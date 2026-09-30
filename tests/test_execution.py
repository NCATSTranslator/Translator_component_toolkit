"""Phase 2 contracts: defaults, isolation, durable outcomes and interfaces."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import hashlib
import importlib
import json
import sqlite3

import pytest

from TCT import execution
from TCT.execution import ExecutionRecordingError, capture_trapi, submit_with_context
from TCT.interfaces.invocation import invoke, ToolInvocationError
from TCT.interfaces import observability
from TCT.journal import Journal


@capture_trapi("message")
def echo(value):
    return value


def records(store):
    with sqlite3.connect(store / "journal.sqlite3") as db:
        rows = db.execute(
            "SELECT status, event_hash FROM calls ORDER BY rowid"
        ).fetchall()
    return [
        (
            status,
            json.loads((store / "artifacts" / digest).read_text()) if digest else None,
        )
        for status, digest in rows
    ]


def test_disabled_has_no_storage_or_capture(monkeypatch, tmp_path):
    module = importlib.import_module("TCT.execution")
    monkeypatch.delenv("TCT_LANGFUSE_ENABLED", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled path performed evidence work")

    monkeypatch.setattr(module, "deepcopy", forbidden)
    monkeypatch.setattr(module, "uuid4", forbidden)
    with execution({"store": str(tmp_path / "unused"), "cache": False}) as run:
        assert run is None
        assert echo("x") == "x"
        assert invoke(echo, "y") == "y"
    assert not (tmp_path / "unused").exists()


def test_durable_native_identity_and_artifact_checksums(tmp_path):
    native = {"message": {"results": []}}
    with execution({"record": True, "store": str(tmp_path)}) as run:
        assert invoke(echo, native) is native
    saved = records(tmp_path)
    assert len(run) == len(saved) == 1
    assert saved[0][0] == "succeeded"
    assert saved[0][1]["output"] == native
    assert saved[0][1]["run_id"] == run.run_id
    for path in (tmp_path / "artifacts").iterdir():
        assert path.name == hashlib.sha256(path.read_bytes()).hexdigest()
    native.clear()
    assert saved[0][1]["output"] == {"message": {"results": []}}


def test_tracing_and_recording_are_independent(monkeypatch, tmp_path):
    monkeypatch.setenv("TCT_LANGFUSE_ENABLED", "true")
    with execution({"record": True, "store": str(tmp_path), "langfuse": False}):
        assert not observability.langfuse_enabled()
        echo(1)
    with execution({"langfuse": True}) as run:
        assert run is None
        assert observability.langfuse_enabled()
        with execution({"langfuse": False}):
            assert not observability.langfuse_enabled()
        assert observability.langfuse_enabled()
    assert len(records(tmp_path)) == 1


def test_nested_disable_and_inherit(tmp_path):
    with execution({"record": True, "trapi": True, "store": str(tmp_path)}) as outer:
        echo({"one": 1})
        with execution({"record": False, "trapi": False}) as disabled:
            assert disabled is None
            echo({"two": 2})
        with execution() as inherited:
            assert inherited is outer
            echo({"three": 3})
    assert len(outer) == len(records(tmp_path)) == 2


def test_one_observation_and_correlated_langfuse(monkeypatch, tmp_path):
    from TCT.interfaces import telemetry

    observed = []

    class Observation:
        def update(self, **kwargs):
            pass

    @contextmanager
    def observe(**kwargs):
        observed.append(kwargs["metadata"])
        yield Observation()

    monkeypatch.setattr(telemetry, "observe_tool", observe)
    with execution({"record": True, "store": str(tmp_path), "trapi": True}) as run:
        invoke(echo, {"results": []}, _interface="mcp")
    assert len(observed) == len(run) == len(records(tmp_path)) == 1
    assert observed[0]["tct.execution.call_id"] == run[0]["call_id"]
    assert observed[0]["tct.execution.run_id"] == run.run_id


def test_explicit_dependencies_and_duplicate_step(tmp_path):
    config = {"record": True, "store": str(tmp_path), "run_id": "shared"}
    with execution(config | {"step_id": "one"}):
        echo(1)
    with execution(config | {"step_id": "two", "depends_on": ["one"]}):
        echo(2)
    with execution(config | {"step_id": "three", "depends_on": ["missing"]}):
        with pytest.raises(ExecutionRecordingError, match="Dependency") as caught:
            echo(3)
        assert caught.value.operation_completed is False
    with execution(config | {"step_id": "one"}):
        with pytest.raises(ExecutionRecordingError, match="already recorded"):
            echo(4)
    assert len(records(tmp_path)) == 2


def test_worker_propagation_and_parent_relationship(tmp_path):
    @capture_trapi("message")
    def parent():
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [submit_with_context(pool, echo, i) for i in range(4)]
            return [future.result() for future in futures]

    with execution({"record": True, "store": str(tmp_path)}) as run:
        assert parent() == [0, 1, 2, 3]
    assert len(records(tmp_path)) == 5
    root = next(r for r in run if r["operation"] == "parent")
    children = [r for r in run if r["operation"] == "echo"]
    assert all(r["parent_call_id"] == root["call_id"] for r in children)
    assert all(r["depends_on"] == [] for r in children)


def test_async_runs_are_isolated():
    async def worker(value):
        with execution({"trapi": True}) as run:
            await asyncio.sleep(0)
            echo(value)
            return run

    async def both():
        return await asyncio.gather(worker(1), worker(2))

    first, second = asyncio.run(both())
    assert first.run_id != second.run_id
    assert [r["output"] for r in first] == [1]
    assert [r["output"] for r in second] == [2]


def test_original_failure_survives_journal_failure(monkeypatch, tmp_path):
    error = RuntimeError("original")

    @capture_trapi("message")
    def fail():
        raise error

    def broken(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Journal, "finish", broken)
    with execution({"record": True, "store": str(tmp_path)}):
        with pytest.raises(RuntimeError) as caught:
            fail()
    assert caught.value is error
    assert records(tmp_path) == [("running", None)]


def test_successful_call_reports_storage_failure(monkeypatch, tmp_path):
    calls = []

    @capture_trapi("message")
    def succeed():
        calls.append(1)
        return 42

    def broken(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(Journal, "finish", broken)
    with execution({"record": True, "store": str(tmp_path)}):
        with pytest.raises(ExecutionRecordingError) as caught:
            succeed()
    assert calls == [1]
    assert caught.value.operation_completed is True


def test_pre_call_failure_does_not_execute(monkeypatch, tmp_path):
    calls = []

    def fail(*args):
        raise OSError("no space")

    monkeypatch.setattr(Journal, "begin", fail)
    with execution({"record": True, "store": str(tmp_path)}):
        with pytest.raises(ToolInvocationError) as caught:
            invoke(lambda: calls.append(1))
    assert calls == []
    assert caught.value.cause.operation_completed is False


@pytest.mark.parametrize(
    "settings",
    [
        {"record": True},
        {"cache": True},
        {"trapi": "yes"},
        {"unknown": True},
        {"depends_on": ["x"]},
        {"run_id": ""},
        {"depends_on": ["x", "x"]},
    ],
)
def test_invalid_configuration(settings):
    with pytest.raises(ValueError):
        with execution(settings):
            pytest.fail("invalid config accepted")


def test_cli_recording_preserves_stdout(tmp_path, capsys):
    from TCT.interfaces.cli import main

    config = tmp_path / "execution.json"
    config.write_text(
        json.dumps(
            {
                "record": True,
                "store": str(tmp_path / "store"),
                "run_id": "cli",
                "step_id": "check",
            }
        )
    )
    workflow = {
        "schema_version": 1,
        "steps": [{"id": "x", "op": "literal", "value": 1}],
        "outputs": {"x": {"$ref": "x"}},
    }
    argv = ["validate-query-workflow", "--workflow", json.dumps(workflow)]
    assert main(argv) == 0
    baseline = capsys.readouterr().out
    assert main(argv + ["--execution", str(config)]) == 0
    assert capsys.readouterr().out == baseline
    assert len(records(tmp_path / "store")) == 1
    assert main(argv + ["--execution", str(tmp_path / "missing")]) == 1
    capsys.readouterr()


def test_mcp_recording_keeps_native_payload(tmp_path):
    from TCT.interfaces.mcp import mcp

    async def run():
        registry = await mcp.get_tools()
        workflow = {
            "schema_version": 1,
            "steps": [{"id": "x", "op": "literal", "value": 1}],
            "outputs": {"x": {"$ref": "x"}},
        }
        tool = registry["validate_query_workflow"]
        baseline = await tool.run({"workflow": workflow})
        recorded = await tool.run(
            {
                "workflow": workflow,
                "execution": {"record": True, "store": str(tmp_path), "run_id": "mcp"},
            }
        )
        assert baseline.structured_content == recorded.structured_content

    asyncio.run(run())
    assert len(records(tmp_path)) == 1


def test_concurrent_duplicate_step_executes_once(tmp_path):
    config = {
        "record": True,
        "store": str(tmp_path),
        "run_id": "same",
        "step_id": "same",
    }
    called = []

    def task():
        with execution(config):
            try:
                invoke(lambda: called.append(1))
                return "executed"
            except ToolInvocationError:
                return "duplicate"

    # Initialize before contention to isolate transactional step registration.
    Journal(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: task(), range(2)))
    assert sorted(outcomes) == ["duplicate", "executed"]
    assert called == [1]


def test_interface_recording_requires_run_id(tmp_path):
    from TCT.execution import interface_execution

    with pytest.raises(ValueError, match="run_id"):
        with interface_execution({"record": True, "store": str(tmp_path)}):
            pytest.fail("accepted missing ID")
    assert not (tmp_path / "journal.sqlite3").exists()


def test_disabled_recording_does_not_reuse_parent_call_id(monkeypatch):
    from TCT.interfaces import telemetry

    seen = []

    @contextmanager
    def observe(**kwargs):
        seen.append(kwargs["metadata"])
        yield None

    monkeypatch.setattr(telemetry, "observe_tool", observe)

    @capture_trapi("message")
    def parent():
        with execution({"trapi": False, "langfuse": True}):
            echo("inner")
        return "outer"

    with execution({"trapi": True}):
        parent()
    assert "tct.execution.call_id" in seen[0]
    assert "tct.execution.call_id" not in seen[1]
