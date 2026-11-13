"""Optional representations preserve execution, native results and evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from TCT.interfaces import tools
from TCT.trapi_representation import represent_trapi
from TCT.execution import execution, capture_trapi


@pytest.mark.parametrize(
    ("name", "backend", "args", "native"),
    [
        (
            "query_knowledge_provider",
            "query_KP",
            ["kp", {}, {}, {}],
            {"knowledge_graph": {"nodes": {}, "edges": {}}},
        ),
        (
            "parallel_query_apis",
            "parallel_api_query",
            [{}, [], {}, {}],
            {"e": {"subject": "X:1", "object": "X:2"}},
        ),
        (
            "neighborhood_finder",
            "tct_neighborhood_finder",
            [[], []],
            SimpleNamespace(raw={"results": []}),
        ),
        (
            "path_finder",
            "query_TCT_pathfinder",
            ["X:1", "X:2"],
            SimpleNamespace(raw={"results": []}),
        ),
    ],
)
def test_optional_wrappers_preserve_result_and_call_once(
    monkeypatch, name, backend, args, native
):
    calls = []

    def invoke(*args, **kwargs):
        calls.append((args, kwargs))
        return native

    monkeypatch.setattr(tools, backend, invoke)
    monkeypatch.setattr(tools, "_get_translator_resources", lambda: {})
    assert getattr(tools, name)(*args) is native
    baseline = calls.pop()
    with execution({"trapi": True}) as records:
        wrapped = getattr(tools, name)(*args)
    assert calls == [baseline]
    assert wrapped is native
    assert records[0]["trapi"]["schema_validation"] == "not_performed"


def test_detached_sidecar_and_unknown_empty():
    native = {
        "knowledge_graph": {
            "edges": {"e": {"sources": [{"resource_id": "infores:test"}]}}
        }
    }
    original = deepcopy(native)
    sidecar = represent_trapi(native, "message")
    sidecar["artifacts"][0]["content"]["message"].clear()
    assert native == original
    assert represent_trapi(None, "message")["artifacts"] == []


def test_workflow_representation_keeps_each_step_and_failures():
    bundle = {
        "steps": {
            "one": {
                "op": "query",
                "status": "succeeded",
                "inputs": {"query": {"message": {}}},
                "response": {"message": {"results": []}},
            },
            "two": {
                "op": "query",
                "status": "failed",
                "inputs": {"query": {"message": {}}},
            },
            "three": {"op": "query", "status": "skipped"},
            "filter": {"op": "filter", "status": "succeeded"},
        }
    }
    artifacts = represent_trapi(bundle, "workflow")["artifacts"]
    assert [(a["step_id"], a["kind"]) for a in artifacts] == [
        ("one", "query"),
        ("one", "response"),
        ("two", "query"),
    ]


def test_wrapped_bundle_still_replays():
    recipe = {
        "schema_version": 1,
        "steps": [{"id": "data", "op": "literal", "value": ["X:1"]}],
        "outputs": {"ids": {"$ref": "data"}},
    }
    with execution({"trapi": True}) as records:
        bundle = tools.run_query_workflow(recipe)
        replayed = tools.replay_query_workflow(bundle)
    assert replayed["outputs"] == {"ids": ["X:1"]}
    assert records[0]["trapi"]["artifacts"] == []


def test_cli_optional_representation(capsys):
    import json
    from TCT.interfaces.cli import main

    recipe = {
        "schema_version": 1,
        "steps": [{"id": "x", "op": "literal", "value": 1}],
        "outputs": {"x": {"$ref": "x"}},
    }
    assert main(["run-query-workflow", "--workflow", json.dumps(recipe)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["outputs"] == {"x": 1}
    assert "trapi" not in output


def test_mcp_optional_representation():
    import asyncio
    from TCT.interfaces.mcp import mcp

    async def run():
        registry = await mcp.get_tools()
        recipe = {
            "schema_version": 1,
            "steps": [{"id": "x", "op": "literal", "value": 1}],
            "outputs": {"x": {"$ref": "x"}},
        }
        output = await registry["run_query_workflow"].run({"workflow": recipe})
        assert output.structured_content["outputs"] == {"x": 1}
        assert "trapi" not in output.structured_content

    asyncio.run(run())


def test_disabled_fast_path_and_nested_disable(monkeypatch):
    @capture_trapi("message")
    def sample():
        return {"results": []}

    with execution({"trapi": True}) as records:
        sample()
        with execution({"trapi": False}):
            sample()
        with execution():
            sample()
    assert len(records) == 2

    def forbidden(*args, **kwargs):
        raise AssertionError("disabled capture converted a payload")

    import importlib

    monkeypatch.setattr(
        importlib.import_module("TCT.execution"), "represent_trapi", forbidden
    )
    assert sample() == {"results": []}


def test_failure_identity_and_no_retry():
    error = ValueError("original")

    @capture_trapi("message")
    def fail():
        raise error

    with execution({"trapi": True}) as records:
        with pytest.raises(ValueError) as caught:
            fail()
    assert caught.value is error
    assert len(records) == 1
    assert records[0]["status"] == "failed"


def test_capture_error_preserves_native_result():
    native = object()

    @capture_trapi("finder")
    def sample():
        return native

    with execution({"trapi": True}) as records:
        assert sample() is native
    assert records[0]["status"] == "succeeded"
    assert records[0]["capture_error"] == "AttributeError"


def test_input_capture_failure_does_not_change_execution():
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("cannot copy")

    @capture_trapi("message")
    def sample(value):
        return None

    with execution({"trapi": True}) as records:
        assert sample(Uncopyable()) is None
    assert records[0]["input_capture_error"] == "RuntimeError"
    assert records[0]["status"] == "succeeded"


def test_async_contexts_are_isolated():
    import asyncio

    @capture_trapi("message")
    def sample(value):
        return {"value": value}

    async def run(value):
        with execution({"trapi": True}) as records:
            await asyncio.sleep(0)
            sample(value)
            return records

    async def both():
        return await asyncio.gather(run(1), run(2))

    first, second = asyncio.run(both())
    assert first[0]["inputs"] == {"value": 1}
    assert second[0]["inputs"] == {"value": 2}
    assert first is not second
