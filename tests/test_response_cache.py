"""Phase 5: cache identity, policy epochs, failures, and offline replay."""

from concurrent.futures import ThreadPoolExecutor
import asyncio
from copy import deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path

import pytest
import requests

from TCT.execution import execution, submit_with_context, capture_operation
from TCT.response_cache import CacheError, CacheReplayError, CacheStore
from TCT.service_capture import capture_request


def response(payload=None, status=200):
    r = requests.Response()
    r.status_code = status
    r._content = json.dumps({"value": 1} if payload is None else payload).encode()
    r._content_consumed = True
    r.headers["Content-Type"] = "application/json"
    r.url = "https://synthetic.invalid/query"
    r.raw = BytesIO(r.content)
    return r


@pytest.fixture
def transport():
    calls = []

    def send(url, **kwargs):
        calls.append(deepcopy(kwargs))
        return response()

    return send, calls


@capture_operation()
def fetch(
    send, *, kind="normalization", url="https://synthetic.invalid/query", **kwargs
):
    return capture_request(send, url, method="post", cache_kind=kind, **kwargs)


def cross(tmp_path, **policy):
    return {
        "store": str(tmp_path),
        "cache": {
            "scope": "cross_run",
            "authorization_partition": "synthetic-public",
            **policy,
        },
    }


def test_default_cache_is_memory_only_and_independent(transport, tmp_path):
    send, calls = transport
    with execution({"cache": True, "langfuse": False}) as run:
        first = fetch(send, json={"x": 1})
        first._content = b'{"mutated": true}'
        assert fetch(send, json={"x": 1}).json() == {"value": 1}
        assert list(run) == []
        assert [e["outcome"] for e in run.cache_events] == ["cold", "warm"]
    with execution({"cache": True}):
        fetch(send, json={"x": 1})
    assert len(calls) == 2
    assert not list(tmp_path.iterdir())


def test_nested_disable_and_policy_override(transport):
    send, calls = transport
    with execution({"cache": {"epoch": "a"}}) as outer:
        fetch(send)
        with execution({"cache": False}) as disabled:
            assert disabled is None
            fetch(send)
        with execution({"cache": {"mode": "bypass"}}) as inner:
            assert inner is outer
            fetch(send)
        fetch(send)
    assert len(calls) == 3
    assert [e["outcome"] for e in outer.cache_events] == ["cold", "bypassed", "warm"]


@pytest.mark.parametrize(
    "kind,ttl", [("normalization", 86400), ("capabilities", 3600), ("trapi", 900)]
)
def test_cross_run_expiry_and_run_pinning(monkeypatch, tmp_path, kind, ttl):
    now = [1000]
    monkeypatch.setattr("TCT.response_cache.time.time", lambda: now[0])
    calls = []

    def send(*a, **kw):
        calls.append(1)
        return response(
            {"message": {"knowledge_graph": {"nodes": {}, "edges": {}}, "results": []}}
        )

    with execution(cross(tmp_path)):
        fetch(send, kind=kind)
    now[0] += ttl - 1
    with execution(cross(tmp_path)) as pinned:
        fetch(send, kind=kind)
        now[0] += 2
        fetch(send, kind=kind)
    assert [e["outcome"] for e in pinned.cache_events] == ["warm", "warm"]
    with execution(cross(tmp_path)) as expired:
        fetch(send, kind=kind)
    assert expired.cache_events[0]["outcome"] == "cold"
    assert len(calls) == 2


def test_persistent_within_run_never_leaks_to_another_run(tmp_path, transport):
    send, calls = transport
    config = {"cache": True, "store": str(tmp_path), "run_id": "one"}
    for settings in [config, config, config | {"run_id": "two"}]:
        with execution(settings):
            fetch(send)
    assert len(calls) == 2
    assert not (tmp_path / "journal.sqlite3").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"epoch": "new"},
        {"dataset_versions": {"provider": "2"}},
        {"dataset_versions": {"normalizer": "2"}},
        {"authorization_partition": "another-user"},
    ],
)
def test_identity_invalidates_when_any_declared_dependency_changes(
    tmp_path, transport, change
):
    send, calls = transport
    with execution(cross(tmp_path)) as before:
        fetch(send, json={"q": [1, 2]})
    with execution(cross(tmp_path, **change)) as after:
        fetch(send, json={"q": [1, 2]})
    assert len(calls) == 2
    assert (
        before.cache_events[0]["original_request_hash"]
        == after.cache_events[0]["original_request_hash"]
    )
    assert (
        before.cache_events[0]["effective_execution_hash"]
        != after.cache_events[0]["effective_execution_hash"]
    )


def test_three_hashes_and_only_declared_equivalences(transport):
    send, calls = transport
    with execution({"cache": True}) as run:
        fetch(send, json={"a": 1, "b": [1, 2]})
        fetch(send, json={"b": [1, 2], "a": 1})
        fetch(send, json={"a": 1, "b": [2, 1]})
        fetch(send, url="https://other.invalid/query", json={"a": 1, "b": [1, 2]})
    first, equal, ordered, endpoint = run.cache_events
    assert first["original_request_hash"] == equal["original_request_hash"]
    assert len({e["effective_execution_hash"] for e in [first, ordered, endpoint]}) == 3
    assert (
        first["response_content_hash"] == hashlib.sha256(response().content).hexdigest()
    )
    assert len(calls) == 3


@pytest.mark.parametrize("arguments", [{"json": {1: "value"}}, {"timeout": (1, 2)}])
def test_undeclared_json_coercions_are_rejected(transport, arguments):
    send, calls = transport
    with execution({"cache": True}), pytest.raises(CacheError, match="JSON"):
        fetch(send, **arguments)
    assert calls == []


def test_reformulation_records_original_and_effective_requests(transport):
    send, calls = transport
    with execution({"cache": True}) as run:
        fetch(
            send,
            json={"predicates": ["a"]},
            original_arguments={"json": {"predicates": ["a", "b"]}},
            reformulation="predicate-pruning.v1",
        )
        fetch(send, json={"predicates": ["a"]})
    one, two = run.cache_events
    assert one["original_request_hash"] != two["original_request_hash"]
    assert one["effective_execution_hash"] == two["effective_execution_hash"]
    assert one["reformulation"] == "predicate-pruning.v1"
    assert len(calls) == 1


def test_refresh_preserves_snapshots_and_replay_order(tmp_path):
    values = iter([1, 2, 3])

    def send(*args, **kwargs):
        return response({"value": next(values)})

    config = {"cache": True, "store": str(tmp_path), "run_id": "original"}
    with execution(config) as run:
        assert fetch(send).json() == {"value": 1}
        with execution({"cache": {"mode": "refresh"}}):
            assert fetch(send).json() == {"value": 2}
        with execution({"cache": {"mode": "bypass"}}):
            assert fetch(send).json() == {"value": 3}
        assert fetch(send).json() == {"value": 2}
    originals = {p.name: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    for event in run.cache_events:
        assert (tmp_path / "artifacts" / event["snapshot_hash"]).exists()
    with execution(
        config
        | {"run_id": "replay", "cache": {"mode": "replay", "snapshot_run": "original"}}
    ) as replay:
        for value in [1, 2, 3, 2]:
            assert fetch(
                lambda *a, **kw: pytest.fail("replay performed HTTP")
            ).json() == {"value": value}
        with pytest.raises(CacheReplayError, match="No remaining snapshot"):
            fetch(send)
    assert all(e["outcome"] == "replayed" for e in replay.cache_events)
    assert originals == {name: (tmp_path / name).read_bytes() for name in originals}


def test_replay_cursor_survives_separate_invocations(tmp_path):
    values = iter([1, 2])

    def send(*a, **kw):
        return response({"value": next(values)})

    with execution(
        {"cache": {"mode": "refresh"}, "store": str(tmp_path), "run_id": "source"}
    ):
        fetch(send)
        fetch(send)
    replay = {
        "cache": {"mode": "replay", "snapshot_run": "source"},
        "store": str(tmp_path),
        "run_id": "target",
    }
    for value in (1, 2):
        with execution(replay):
            assert fetch(lambda *a, **kw: pytest.fail("network")).json() == {
                "value": value
            }
    with execution(replay), pytest.raises(CacheReplayError):
        fetch(send)
    with execution(replay | {"run_id": "intentional-resample"}):
        assert fetch(send).json() == {"value": 1}


@pytest.mark.parametrize(
    "record,trapi", [(False, False), (True, False), (False, True), (True, True)]
)
def test_cache_capture_combinations_remain_independent(
    record, trapi, tmp_path, transport
):
    send, calls = transport
    with execution(
        {
            "cache": True,
            "record": record,
            "trapi": trapi,
            "langfuse": False,
            "store": str(tmp_path),
        }
    ) as run:
        fetch(send)
        fetch(send)
    assert len(calls) == 1
    assert len(run) == (2 if record or trapi else 0)
    assert (tmp_path / "journal.sqlite3").exists() is record
    if record or trapi:
        assert run[1]["observations"][0]["cache"]["outcome"] == "warm"


@pytest.mark.parametrize(
    "payload,status",
    [
        ({}, 503),
        ({"error": "failed"}, 200),
        ({"status": "ERROR"}, 200),
        ("bad shape", 200),
    ],
)
def test_unsuccessful_responses_are_observed_but_never_hits(tmp_path, payload, status):
    calls = []

    def send(*a, **kw):
        calls.append(1)
        return response(payload, status)

    with execution({"cache": True, "store": str(tmp_path)}) as run:
        fetch(send)
        fetch(send)
    assert len(calls) == 2
    assert all(e["status"] == "not_cacheable" for e in run.cache_events)


def test_transport_failure_is_not_an_empty_result_and_can_replay(tmp_path):
    def send(*a, **kw):
        raise requests.Timeout("synthetic timeout")

    with execution({"cache": True, "store": str(tmp_path), "run_id": "failed"}):
        with pytest.raises(requests.Timeout):
            fetch(send)
    with execution(
        {"store": str(tmp_path), "cache": {"mode": "replay", "snapshot_run": "failed"}}
    ) as run:
        with pytest.raises(requests.Timeout, match="Replayed transport failure"):
            fetch(lambda *a, **kw: pytest.fail("network"))
    assert run.cache_events[0]["response_content_hash"] is None


def test_failed_refresh_does_not_replace_previous_success(transport):
    send, _ = transport
    with execution({"cache": True}):
        fetch(send)
        with execution({"cache": {"mode": "refresh"}}):
            assert fetch(lambda *a, **kw: response({}, 500)).status_code == 500
        assert fetch(lambda *a, **kw: pytest.fail("cached success lost")).json() == {
            "value": 1
        }


def test_tampered_snapshot_fails_closed(tmp_path, transport):
    send, _ = transport
    with execution({"cache": True, "store": str(tmp_path), "run_id": "source"}) as run:
        fetch(send)
    (tmp_path / "artifacts" / run.cache_events[0]["snapshot_hash"]).write_text("{}")
    with execution(
        {"store": str(tmp_path), "cache": {"mode": "replay", "snapshot_run": "source"}}
    ):
        with pytest.raises(CacheReplayError, match="checksum"):
            fetch(lambda *a, **kw: pytest.fail("network"))


def test_storage_failure_reports_completed_call(monkeypatch, tmp_path, transport):
    send, calls = transport

    def broken(*a, **kw):
        raise OSError("synthetic full disk")

    monkeypatch.setattr(CacheStore, "save", broken)
    with execution({"cache": True, "store": str(tmp_path)}):
        with pytest.raises(CacheError) as error:
            fetch(send)
    assert error.value.operation_completed is True
    assert len(calls) == 1


def test_workers_share_context_but_runs_do_not(transport):
    send, calls = transport
    with execution({"cache": True}) as run, ThreadPoolExecutor(4) as pool:
        fetch(send)
        outputs = [submit_with_context(pool, fetch, send) for _ in range(8)]
        assert all(f.result().json() == {"value": 1} for f in outputs)
    assert len(calls) == 1
    assert len(run.cache_events) == 9


@pytest.mark.parametrize(
    "policy",
    [
        None,
        1,
        "use",
        {"scope": "global"},
        {"scope": "cross_run"},
        {"mode": "replay"},
        {"ttl": {"trapi": -1}},
        {"ttl": {"unknown": 1}},
        {"dataset_versions": {"provider": None}},
    ],
)
def test_invalid_policies_are_rejected_before_calls(policy):
    with pytest.raises(ValueError):
        with execution({"cache": policy}):
            pytest.fail("invalid configuration")


def test_authenticated_cache_requires_explicit_partition(transport):
    send, calls = transport
    with execution({"cache": True}):
        with pytest.raises(CacheError, match="authorization_partition"):
            fetch(send, headers={"Authorization": "synthetic-secret"})
    assert calls == []


@pytest.mark.parametrize("interface", ["cli", "mcp"])
def test_persistent_cache_through_explicit_interface_settings(
    interface, monkeypatch, tmp_path, capsys
):
    from TCT.interfaces.cli import main
    from TCT.interfaces.mcp import mcp

    payload = json.loads(
        (Path(__file__).parent / "fixtures/rollup/normalization.json").read_text()
    )
    calls = []

    def frozen(*a, **kw):
        calls.append(1)
        return response(payload)

    monkeypatch.setattr(requests.sessions.Session, "request", frozen)
    config = {"cache": True, "store": str(tmp_path), "run_id": "interface-run"}

    def call(config):
        if interface == "cli":
            path = tmp_path / "execution.json"
            path.write_text(json.dumps(config))
            assert (
                main(
                    [
                        "normalize-nodes",
                        "--query",
                        "MONDO:0004975",
                        "--execution",
                        str(path),
                    ]
                )
                == 0
            )
            return json.loads(capsys.readouterr().out)

        async def invoke():
            registry = await mcp.get_tools()
            return await registry["normalize_nodes"].run(
                {"query": "MONDO:0004975", "execution": config}
            )

        result = asyncio.run(invoke())
        return result.structured_content or [part.text for part in result.content]

    first = call(config)
    assert call(config) == first
    assert len(calls) == 1
    replay = config | {
        "run_id": "replay",
        "cache": {"mode": "replay", "snapshot_run": "interface-run"},
    }
    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        lambda *a, **kw: pytest.fail("replay network"),
    )
    assert call(replay) == first
    assert call(replay) == first


def test_nested_partial_policy_inherits_required_fields(tmp_path, transport):
    send, calls = transport
    with execution(
        {"store": str(tmp_path), "cache": {"authorization_partition": "public"}}
    ):
        with execution({"cache": {"scope": "cross_run"}}):
            fetch(send)
    assert len(calls) == 1


def test_runtime_and_policy_version_are_execution_dependencies(monkeypatch, transport):
    from TCT.config import RuntimeConfig

    send, calls = transport
    with execution({"cache": True}) as run:
        fetch(send)
        monkeypatch.setattr(
            "TCT.response_cache.get_runtime_config", lambda: RuntimeConfig("prod")
        )
        fetch(send)
        monkeypatch.setattr("TCT.response_cache.POLICY_VERSION", "future-policy")
        fetch(send)
    assert len(calls) == 3
    assert len({e["effective_execution_hash"] for e in run.cache_events}) == 3


def test_workflow_caches_and_replays_complete_bounded_responses(monkeypatch, tmp_path):
    from TCT import workflow

    fixtures = Path(__file__).parent / "fixtures" / "rollup"
    payload = json.loads((fixtures / "gene.json").read_text())
    args = {
        "url": "https://synthetic.invalid/query",
        "timeout_seconds": 10,
        "query": json.loads((fixtures / "case.json").read_text())["queries"]["genes"],
    }
    calls = []

    def send(*a, **kw):
        calls.append(1)
        return response(payload)

    monkeypatch.setattr(requests, "post", send)
    with execution({"cache": True, "store": str(tmp_path), "run_id": "workflow"}):
        for outcome in ["cold", "warm"]:
            record = {}
            assert workflow._query(args, record) == payload
            assert record["cache"]["outcome"] == outcome
    monkeypatch.setattr(
        requests, "post", lambda *a, **kw: pytest.fail("replay network")
    )
    with execution(
        {
            "store": str(tmp_path),
            "cache": {"mode": "replay", "snapshot_run": "workflow"},
        }
    ):
        assert workflow._query(args, {}) == payload
    assert len(calls) == 1


def test_workflow_streaming_limit_is_preserved(monkeypatch, tmp_path):
    from TCT import workflow

    monkeypatch.setattr(workflow, "MAX_RESPONSE_BYTES", 3)
    monkeypatch.setattr(requests, "post", lambda *a, **kw: response({"long": "body"}))
    args = {
        "url": "https://synthetic.invalid/query",
        "timeout_seconds": 10,
        "query": {
            "message": {
                "query_graph": {
                    "nodes": {"a": {}, "b": {}},
                    "edges": {"e": {"subject": "a", "object": "b"}},
                }
            }
        },
    }
    with execution({"cache": True, "store": str(tmp_path)}) as run:
        with pytest.raises(ValueError, match="exceeds 3"):
            workflow._query(args, {})
    assert run.cache_events[0]["status"] == "incomplete_snapshot"
    assert run.cache_events[0]["snapshot_hash"] is None


def test_same_nlq_rollup_in_all_cache_modes(monkeypatch, tmp_path):
    from TCT.config import service_url
    from TCT.evidence import reduce_evidence
    from TCT.interfaces import tools
    from TCT.interfaces.serialization import to_jsonable

    fixtures = Path(__file__).parent / "fixtures" / "rollup"

    def load(name):
        return json.loads((fixtures / (name + ".json")).read_text())

    calls = []
    providers = load("providers")

    def frozen(session, method, url, **kw):
        calls.append(url)
        if url == service_url("smartapi_registry"):
            return response(load("registry"))
        if url.endswith("/get_normalized_nodes"):
            return response(load("normalization"))
        if url in providers.values():
            kind = "genes" if url == providers["gene-provider"] else "chemicals"
            assert kw["json"] == load("case")["queries"][kind]
            return response(load("gene" if kind == "genes" else "chemical"))
        pytest.fail(f"Unexpected request {method} {url}")

    monkeypatch.setattr(requests.sessions.Session, "request", frozen)
    for scenario, mode, count in [
        ("cold", "use", 4),
        ("warm", "use", 0),
        ("refreshed", "refresh", 4),
        ("replayed", "replay", 0),
    ]:
        policy = {"mode": mode}
        if mode == "replay":
            policy["snapshot_run"] = "cold"
            monkeypatch.setattr(
                requests.sessions.Session,
                "request",
                lambda *a, **kw: pytest.fail("replay performed network I/O"),
            )
        before = len(calls)
        with execution(
            cross(tmp_path, **policy) | {"run_id": scenario, "trapi": True}
        ) as run:
            outputs = [
                tools.normalize_nodes(
                    "MONDO:0004975", return_equivalent_identifiers=True
                ),
                tools.get_kp_info(),
            ]
            for kind, provider in [
                ("genes", "gene-provider"),
                ("chemicals", "chemical-provider"),
            ]:
                outputs.append(
                    tools.query_knowledge_provider(
                        provider,
                        load("case")["queries"][kind],
                        outputs[1][1],
                        load("predicates"),
                    )
                )
            for actual, expected in zip(outputs, load("golden")["history"]):
                assert to_jsonable(actual) == expected["output"]
        assert len(calls) - before == count
        assert {e["outcome"] for e in run.cache_events} == {scenario}
        rollup = reduce_evidence(run, load("composition"))
        assert rollup["rollup_hash"] == load("rollup-golden")["rollup_hash"]
