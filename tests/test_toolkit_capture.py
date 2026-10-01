"""Phase 3 compatibility matrix and synthetic service evidence fixtures.

Boundary fixtures intentionally isolate delegation; service fixtures below execute
real conversion/merge code. They are synthetic, not medical goldens.
"""

from base64 import b64decode
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
import requests

from TCT.execution import execution, ExecutionRecordingError
from TCT.interfaces import tools
from TCT.interfaces.invocation import invoke, ToolInvocationError
from TCT.interfaces.serialization import to_jsonable
from TCT import node_normalizer, name_resolver, translator_query, translator_metakg

# Every working public boundary; the broken nineteenth endpoint is excluded.
CASES = [
    ("get_translator_resources", "_get_translator_resources", []),
    ("name_lookup", "lookup", ["term"]),
    ("get_name_synonyms", "synonyms", ["X:1"]),
    ("batch_name_lookup", "batch_lookup", [["term"]]),
    ("normalize_nodes", "get_normalized_nodes", [["X:1"]]),
    ("get_kp_info", "get_translator_kp_info", []),
    ("get_metakg_data", "get_KP_metadata", [{"kp": "https://fixture.invalid"}]),
    (
        "add_custom_api_to_metakg",
        "add_new_API_for_query",
        [{}, [], "kp", "url", "p", "s", "o"],
    ),
    ("add_plover_apis_to_metakg", "add_plover_API", [{}, []]),
    ("get_api_predicates", "get_translator_API_predicates", []),
    ("optimize_query_for_api", "optimize_query_json", [{}, "kp", {}]),
    ("query_knowledge_provider", "query_KP", ["kp", {}, {}, {}]),
    ("parallel_query_apis", "parallel_api_query", [{}, [], {}, {}]),
    ("neighborhood_finder", "tct_neighborhood_finder", [["X:1"], ["biolink:Gene"]]),
    ("path_finder", "query_TCT_pathfinder", ["X:1", "X:2"]),
    ("validate_query_workflow", "validate_workflow", [{}]),
    ("run_query_workflow", "run_workflow", [{}]),
    ("replay_query_workflow", "replay_workflow", [{}]),
]


@pytest.mark.parametrize("name,backend,args", CASES)
@pytest.mark.parametrize("interface", ["python", "shared"])
def test_all_working_boundaries_preserve_identity_arguments_mutations_and_errors(
    monkeypatch, name, backend, args, interface
):
    monkeypatch.setattr(tools, "_get_translator_resources", lambda: {})
    native = (
        SimpleNamespace(raw={})
        if name in {"path_finder", "neighborhood_finder"}
        else {"steps": {}, "native": [1]}
    )
    calls = []
    failure = []

    def delegate(*a, **kw):
        calls.append(deepcopy((a, kw)))
        if failure:
            raise failure[0]
        if a and isinstance(a[0], dict):
            a[0]["mutated"] = True
        return native

    monkeypatch.setattr(tools, backend, delegate)
    tool = getattr(tools, name)
    call = tool if interface == "python" else lambda *a: invoke(tool, *a)
    before = deepcopy(args)
    assert call(*before) is native
    after = deepcopy(args)
    with execution({"trapi": True}) as run:
        assert call(*after) is native
    assert calls[0] == calls[1]
    assert before == after
    assert len(run) == 1  # interface adapter unwraps exactly once
    assert to_jsonable(run[0]["output"]) == to_jsonable(native)
    error = RuntimeError("fixture failure")
    failure.append(error)
    for enabled in [False, True]:
        with execution({"trapi": enabled}) as failed:
            with pytest.raises((RuntimeError, ToolInvocationError)) as caught:
                call(*deepcopy(args))
        assert (
            caught.value.cause
            if isinstance(caught.value, ToolInvocationError)
            else caught.value
        ) is error
        if enabled:
            assert failed[0]["status"] == "failed"
    assert len(calls) == 4


def response(body, status=200):
    value = requests.Response()
    value.status_code = status
    value._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return value


def services(run):
    return [o for r in run for o in r.get("observations", []) if o["kind"] == "service"]


def test_normalizer_retains_equivalence_and_unmatched_without_extra_calls(monkeypatch):
    body = {
        "X:1": {
            "id": {"identifier": "Y:1", "label": "fixture"},
            "type": ["biolink:Gene"],
            "equivalent_identifiers": [{"identifier": "X:1"}],
            "information_content": 42,
        },
        "X:missing": None,
    }
    calls = []

    def get(url, **kwargs):
        calls.append(deepcopy(kwargs))
        return response(body)

    monkeypatch.setattr(requests, "get", get)
    baseline = node_normalizer.get_normalized_nodes(list(body))
    with execution({"trapi": True}) as run:
        captured = node_normalizer.get_normalized_nodes(list(body))
    assert captured == baseline and captured["X:1"].curie_synonyms is None
    assert calls[0] == calls[1] and len(calls) == 2
    assert services(run)[0]["body_json"] == body
    assert json.loads(b64decode(services(run)[0]["body_base64"])) == body
    assert run[0]["inputs"]["return_equivalent_identifiers"] is False


@pytest.mark.parametrize(
    "operation,args,body",
    [
        (
            name_resolver.lookup,
            ["term"],
            [
                {"curie": "X:1", "types": ["Gene"], "names": ["alias"], "score": 12},
                {"curie": "X:2"},
            ],
        ),
        (
            name_resolver.synonyms,
            ["X:1"],
            {"X:1": {"curie": "X:1", "names": ["alias"], "score": 12}},
        ),
        (
            name_resolver.batch_lookup,
            [["term"]],
            {"term": [{"curie": "X:1", "score": 12}]},
        ),
    ],
)
def test_resolution_retains_full_candidates(monkeypatch, operation, args, body):
    calls = []

    def request(url, **kwargs):
        calls.append(kwargs)
        return response(body)

    monkeypatch.setattr(requests, "get", request)
    monkeypatch.setattr(requests, "post", request)
    baseline = operation(*args)
    with execution({"trapi": True}) as run:
        assert operation(*args) == baseline
    assert len(calls) == 2 and calls[0] == calls[1]
    assert services(run)[0]["body_json"] == body


def query():
    return translator_query.format_query_json(
        ["X:1"], predicates=["biolink:affects", "biolink:related_to"]
    )


def test_transform_snapshots_preserve_legacy_mutation():
    original = query()
    with execution({"trapi": True}) as run:
        result = translator_query.optimize_query_json(
            original, "kp", {"kp": ["biolink:affects"]}
        )
    assert result["message"] is original["message"]
    assert run[0]["inputs"]["query_json"] != run[0]["inputs_after"]["query_json"]
    assert run[0]["output"] == original
    assert run[0]["depends_on"] == []


@pytest.mark.parametrize(
    "status,body",
    [
        (200, {"message": {"knowledge_graph": {"edges": {}}}}),
        (503, {"error": "fixture unavailable"}),
        (200, b"not json"),
    ],
)
def test_provider_empty_http_and_parse_failure_remain_distinct(
    monkeypatch, status, body
):
    monkeypatch.setattr(requests, "post", lambda *a, **kw: response(body, status))
    args = (
        "kp",
        query(),
        {"kp": "https://fixture.invalid"},
        {"kp": ["biolink:affects"]},
    )
    if isinstance(body, bytes):
        with pytest.raises(requests.exceptions.JSONDecodeError):
            translator_query.query_KP(*args)
        with execution({"trapi": True}) as run:
            with pytest.raises(requests.exceptions.JSONDecodeError):
                translator_query.query_KP(*args)
        assert services(run)[0]["body_json_status"] == "not_json"
    else:
        assert translator_query.query_KP(*args) is None
        with execution({"trapi": True}) as run:
            assert translator_query.query_KP(*args) is None
        assert services(run)[0]["body_json"] == body
    assert services(run)[0]["status_code"] == status


def test_parallel_capture_retains_envelopes_and_collision_decisions(monkeypatch):
    import concurrent.futures

    # Fix the completion schedule in this subcase; production ordering is unchanged.
    monkeypatch.setattr(
        concurrent.futures, "as_completed", lambda futures: list(futures)
    )
    bodies = {}
    calls = []
    for provider in ["a", "b"]:
        bodies[provider] = {
            "status": "OK",
            "message": {
                "knowledge_graph": {
                    "nodes": {"X:1": {}},
                    "edges": {
                        "collision": {
                            "subject": "X:1",
                            "object": "X:2",
                            "sources": [{"resource_id": provider}],
                            "qualifiers": [
                                {
                                    "qualifier_type_id": "fixture",
                                    "qualifier_value": provider,
                                }
                            ],
                        }
                    },
                },
                "results": [
                    {
                        "analyses": [
                            {
                                "resource_id": provider,
                                "edge_bindings": {"e": [{"id": "collision"}]},
                            }
                        ]
                    }
                ],
                "auxiliary_graphs": {"support": {"edges": ["collision"]}},
            },
        }

    def post(url, **kwargs):
        calls.append((url, deepcopy(kwargs)))
        if url == "failed":
            raise requests.ConnectionError("fixture")
        return response(bodies[url])

    monkeypatch.setattr(requests, "post", post)
    args = (
        query(),
        ["a", "b", "failed"],
        {p: p for p in ["a", "b", "failed"]},
        {p: ["biolink:affects"] for p in ["a", "b", "failed"]},
    )
    baseline = translator_query.parallel_api_query(*args)
    with execution({"trapi": True}) as run:
        captured = translator_query.parallel_api_query(*args)
    # One worker preserves provider completion order for this fixture.
    assert captured == baseline == bodies["b"]["message"]["knowledge_graph"]["edges"]
    assert len(calls) == 6 and calls[:3] == calls[3:]
    assert [o.get("body_json") for o in services(run)] == [
        bodies["a"],
        bodies["b"],
        None,
    ]
    assert services(run)[-1]["status"] == "transport_error"
    merges = [o for o in run[0]["observations"] if o["kind"] == "edge_merge"]
    assert merges[1]["overwritten_edge_ids"] == ["collision"]
    assert all(r["depends_on"] == [] for r in run)


def test_disabled_does_not_read_body(monkeypatch):
    class NativeResponse:
        status_code = 200

        @property
        def content(self):
            raise AssertionError("disabled capture read response")

        def json(self):
            return {"X:1": None}

    monkeypatch.setattr(requests, "get", lambda *a, **kw: NativeResponse())
    assert node_normalizer.get_normalized_nodes("X:1") is None


def test_incomplete_requested_capture_surfaces_after_native_operation(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(
        requests,
        "get",
        lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {"X:1": None}),
    )
    with execution({"record": True, "store": str(tmp_path)}) as run:
        with pytest.raises(ExecutionRecordingError) as caught:
            node_normalizer.get_normalized_nodes("X:1")
    assert caught.value.operation_completed is True
    assert run[0]["status"] == "capture_failed"


def test_working_surface_coverage_and_unsupported_endpoint():
    assert {c[0] for c in CASES} == {f.__name__ for f in tools.TOOLS} - {
        "trapi_query_endpoint"
    }
    assert len(CASES) == 18
    with pytest.raises(TypeError):
        tools.trapi_query_endpoint("https://fixture.invalid")


def test_discovery_metadata_and_cached_resources_keep_full_observations(monkeypatch):
    import pandas as pd
    from TCT import TCT as core
    from TCT.config import service_url

    calls = []
    registry = {
        "hits": [
            {
                "_id": "synthetic",
                "info": {"title": "fixture"},
                "servers": [
                    {"url": "https://fixture.invalid", "x-maturity": "production"}
                ],
                "extra": {"provenance": "synthetic"},
            }
        ]
    }
    metadata = {
        "hits": [{"_id": "Gene-affects-Gene", "extra": {"evidence": "synthetic"}}]
    }
    plover = {
        "nodes": {"biolink:Gene": {"id_prefixes": ["X"]}},
        "edges": [],
        "extra": "synthetic",
    }

    def get(url, **kwargs):
        calls.append((url, kwargs))
        if url == service_url("smartapi_registry"):
            return response(registry)
        if "/metakg" in url:
            return response(metadata)
        if url.endswith("/meta_knowledge_graph"):
            return response(plover)
        raise AssertionError(f"Unexpected request {url}")

    monkeypatch.setattr(requests, "get", get)
    core.clear_translator_resource_cache()
    try:
        baseline = tools.get_translator_resources()
        baseline_calls = deepcopy(calls)
        core.clear_translator_resource_cache()
        calls.clear()
        with execution({"trapi": True}) as run:
            captured = tools.get_translator_resources()
            assert tools.get_translator_resources() is captured
        assert captured.api_names == baseline.api_names
        pd.testing.assert_frame_equal(captured.meta_kg, baseline.meta_kg)
        assert captured.api_predicates == baseline.api_predicates
        assert calls == baseline_calls
        bodies = [o["body_json"] for o in services(run)]
        assert registry in bodies and metadata in bodies and plover in bodies
        assert len(bodies) == len(baseline_calls)
    finally:
        core.clear_translator_resource_cache()


def test_custom_metadata_captures_mapping_mutation_and_dataframe(monkeypatch):
    import pandas as pd

    api_names = {}
    metadata = pd.DataFrame(columns=["API", "Predicate", "Subject", "Object", "URL"])
    with execution({"trapi": True}) as run:
        result = tools.add_custom_api_to_metakg(
            api_names,
            metadata,
            "fixture",
            "https://fixture.invalid",
            "biolink:affects",
            "biolink:ChemicalEntity",
            "biolink:Gene",
        )
    assert result[0] is api_names
    assert len(metadata) == 0 and len(result[1]) == 1
    assert run[0]["inputs"]["api_names"] == {}
    assert run[0]["inputs_after"]["api_names"] == {"fixture": "https://fixture.invalid"}
    assert to_jsonable(result[1]) == [
        {
            "API": "fixture",
            "Predicate": "biolink:affects",
            "Subject": "biolink:ChemicalEntity",
            "Object": "biolink:Gene",
            "URL": "https://fixture.invalid",
        }
    ]


def test_metakg_fallback_preserves_both_attempts(monkeypatch):
    calls = []
    bodies = [{"unavailable": True}, {"hits": [{"_id": "Gene-affects-Gene"}]}]

    def get(url, **kwargs):
        calls.append(url)
        return response(bodies[len(calls) - 1])

    monkeypatch.setattr(requests, "get", get)
    with execution({"trapi": True}) as run:
        result = translator_metakg.get_KP_metadata(
            {"fixture": "https://fixture.invalid"}
        )
    assert len(calls) == 2 and len(result) == 1
    assert [o["body_json"] for o in services(run)] == bodies


def test_finder_assembly_preserves_evidence_and_native_extensions():
    from TCT.TCT_pathfinder import parse_results_for_pathfinder
    from TCT.TCT_neighborhood_finder import parse_results_for_neighborhood_finder

    left = {
        "a": {
            "subject": "X:chemical",
            "object": "X:gene",
            "predicate": "biolink:affects",
            "attributes": [],
            "sources": [{"resource_id": "infores:synthetic"}],
        }
    }
    right = {
        "b": {
            "subject": "X:gene",
            "object": "X:disease",
            "predicate": "biolink:gene_associated_with_condition",
            "attributes": [],
            "sources": [{"resource_id": "infores:synthetic"}],
        }
    }
    expected = parse_results_for_pathfinder(
        "X:chemical", "X:disease", deepcopy(left), deepcopy(right), get_node_info=False
    )
    with execution({"trapi": True}) as run:
        actual = parse_results_for_pathfinder(
            "X:chemical",
            "X:disease",
            deepcopy(left),
            deepcopy(right),
            get_node_info=False,
        )
    assert actual == expected
    assert set(actual["knowledge_graph"]["edges"]) == {"a", "b"}
    assert actual["auxiliary_graphs"] == {"aux_1_X:gene": ["a", "b"]}
    assert run[0]["inputs"]["result1"] == left
    assert run[0]["inputs"]["result2"] == right
    baseline = parse_results_for_neighborhood_finder(
        "X:chemical", deepcopy(left), get_node_info=False
    )
    with execution({"trapi": True}) as run:
        captured = parse_results_for_neighborhood_finder(
            "X:chemical", deepcopy(left), get_node_info=False
        )
    assert baseline == captured
    assert captured["knowledge_graph"]["edges"] == left


def test_parallel_does_not_swallow_requested_recording_failure(monkeypatch, tmp_path):
    from TCT.journal import Journal

    original = Journal.finish

    def finish(self, record):
        if record["operation"] == "query_KP":
            raise OSError("fixture disk failure")
        return original(self, record)

    monkeypatch.setattr(Journal, "finish", finish)
    monkeypatch.setattr(
        requests,
        "post",
        lambda *a, **kw: response({"message": {"knowledge_graph": {"edges": {}}}}),
    )
    with execution({"record": True, "store": str(tmp_path)}):
        with pytest.raises(ExecutionRecordingError):
            translator_query.parallel_api_query(
                query(),
                ["kp"],
                {"kp": "https://fixture.invalid"},
                {"kp": ["biolink:affects"]},
            )


@pytest.mark.parametrize("name,backend,args", CASES)
def test_cli_and_mcp_payloads_with_durable_capture(
    monkeypatch, tmp_path, capsys, name, backend, args
):
    import asyncio
    import inspect
    from typing import Any, get_type_hints
    from TCT.interfaces.cli import main
    from TCT.interfaces.mcp import mcp

    monkeypatch.setattr(tools, "_get_translator_resources", lambda: {})
    native = (
        SimpleNamespace(raw={})
        if name in {"path_finder", "neighborhood_finder"}
        else {"steps": {}, "fixture": [1]}
    )
    calls = []

    def delegate(*a, **kw):
        calls.append(deepcopy((a, kw)))
        return native

    monkeypatch.setattr(tools, backend, delegate)
    tool = getattr(tools, name)
    arguments = dict(inspect.signature(tool).bind(*args).arguments)
    argv = [name.replace("_", "-")]
    hints = get_type_hints(tool)
    for key, value in arguments.items():
        argv.append("--" + key.replace("_", "-"))
        if isinstance(value, list) and hints[key] is not Any:
            argv.extend(value or ["fixture"])
        elif isinstance(value, (dict, list)):
            argv.append(json.dumps(value))
        else:
            argv.append(str(value))
    assert main(argv) == 0
    before = capsys.readouterr()
    config = {
        "record": True,
        "store": str(tmp_path / "store"),
        "run_id": name,
        "trapi": True,
    }
    path = tmp_path / "execution.json"
    path.write_text(json.dumps(config))
    assert main(argv + ["--execution", str(path)]) == 0
    after = capsys.readouterr()
    assert before == after
    assert calls[0] == calls[1]

    async def invoke_mcp():
        registered = await mcp.get_tool(name)
        baseline = await registered.run(deepcopy(arguments))
        captured = await registered.run(deepcopy(arguments) | {"execution": config})
        assert to_jsonable(baseline.content) == to_jsonable(captured.content)
        assert to_jsonable(baseline.structured_content) == to_jsonable(
            captured.structured_content
        )

    asyncio.run(invoke_mcp())
    assert calls[2] == calls[3]
