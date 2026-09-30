"""Optional representations preserve execution, native results and evidence."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from TCT.interfaces import tools
from TCT.trapi_representation import with_trapi


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
    wrapped = getattr(tools, name)(*args, include_trapi=True)
    assert calls == [baseline]
    assert wrapped["result"] is native
    assert wrapped["trapi"]["schema_validation"] == "not_performed"


def test_detached_sidecar_and_unknown_empty():
    native = {
        "knowledge_graph": {
            "edges": {"e": {"sources": [{"resource_id": "infores:test"}]}}
        }
    }
    original = deepcopy(native)
    sidecar = with_trapi(native, "message")
    sidecar["trapi"]["artifacts"][0]["content"]["message"].clear()
    assert native == original
    assert with_trapi(None, "message")["trapi"]["artifacts"] == []


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
    artifacts = with_trapi(bundle, "workflow")["trapi"]["artifacts"]
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
    envelope = tools.run_query_workflow(recipe, include_trapi=True)
    replayed = tools.replay_query_workflow(envelope["result"], include_trapi=True)
    assert replayed["result"]["outputs"] == {"ids": ["X:1"]}
    assert envelope["trapi"]["artifacts"] == []


def test_cli_optional_representation(capsys):
    import json
    from TCT.interfaces.cli import main

    recipe = {
        "schema_version": 1,
        "steps": [{"id": "x", "op": "literal", "value": 1}],
        "outputs": {"x": {"$ref": "x"}},
    }
    assert (
        main(
            ["run-query-workflow", "--workflow", json.dumps(recipe), "--include-trapi"]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["result"]["outputs"] == {"x": 1}
    assert output["trapi"]["schema_validation"] == "not_performed"


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
        output = await registry["run_query_workflow"].run(
            {"workflow": recipe, "include_trapi": True}
        )
        assert output.structured_content["result"]["outputs"] == {"x": 1}
        assert output.structured_content["trapi"]["artifacts"] == []

    asyncio.run(run())
