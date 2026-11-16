"""End-to-end query composition against a controlled local HTTP provider."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

import pytest
import requests

from TCT import replay_workflow, run_workflow, validate_workflow
from TCT import workflow as engine
from TCT.interfaces import cli


def ref(step, path=""):
    return {"$ref": step, "path": path}


def trapi(edges):
    nodes = {
        edge[key]: {"categories": ["biolink:NamedThing"]}
        for edge in edges.values()
        for key in ("subject", "object")
    }
    return {
        "message": {
            "knowledge_graph": {"nodes": nodes, "edges": edges},
            "auxiliary_graphs": {},
            "results": [
                {
                    "node_bindings": {
                        "n0": [{"id": edge["subject"]}],
                        "n1": [{"id": edge["object"]}],
                    },
                    "analyses": [
                        {
                            "resource_id": "infores:fixture",
                            "edge_bindings": {"e0": [{"id": key}]},
                        }
                    ],
                }
                for key, edge in edges.items()
            ],
        }
    }


FIRST = trapi(
    {
        "e/a~1": {
            "subject": "EXAMPLE:drug",
            "predicate": "biolink:affects",
            "object": "EXAMPLE:gene1",
            "qualifiers": [
                {
                    "qualifier_type_id": "biolink:object_direction_qualifier",
                    "qualifier_value": "decreased",
                }
            ],
            "sources": [
                {
                    "resource_id": "infores:fixture",
                    "resource_role": "primary_knowledge_source",
                }
            ],
        },
        "e2": {
            "subject": "EXAMPLE:drug",
            "predicate": "biolink:related_to",
            "object": "EXAMPLE:gene2",
        },
        "e3": {
            "subject": "EXAMPLE:drug",
            "predicate": "biolink:affects",
            "object": "EXAMPLE:gene1",
        },
    }
)
SECOND = trapi(
    {
        "f1": {
            "subject": "EXAMPLE:gene1",
            "predicate": "biolink:associated_with",
            "object": "EXAMPLE:disease",
        },
        "f2": {
            "subject": "EXAMPLE:gene2",
            "predicate": "biolink:associated_with",
            "object": "EXAMPLE:disease",
        },
    }
)


@pytest.fixture
def provider():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(
                (
                    self.path,
                    json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                )
            )
            status, payload = {
                "/first": (200, FIRST),
                "/second": (200, SECOND),
                "/empty": (200, trapi({})),
                "/fail": (503, {"error": "unavailable"}),
                "/pending": (202, {"job": "pending"}),
                "/application-error": (200, {"status": "Error", "message": {}}),
                "/malformed": (200, {"message": {}}),
                "/redirect": (302, {"location": "/first"}),
            }.get(self.path, (200, "not JSON"))
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps(payload) if isinstance(payload, dict) else payload
            self.wfile.write(body.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def query(ids):
    return {
        "message": {
            "query_graph": {
                "nodes": {
                    "n0": {"ids": ids},
                    "n1": {"categories": ["biolink:NamedThing"]},
                },
                "edges": {
                    "e0": {
                        "subject": "n0",
                        "object": "n1",
                        "predicates": ["biolink:related_to"],
                    }
                },
            }
        }
    }


def recipe(base):
    return {
        "schema_version": 1,
        "steps": [
            {
                "id": "first",
                "op": "query",
                "url": base + "/first",
                "query": query(["EXAMPLE:drug"]),
            },
            {
                "id": "edges",
                "op": "rows",
                "input": ref("first", "/message/knowledge_graph/edges"),
            },
            {
                "id": "filtered",
                "op": "filter",
                "input": ref("edges"),
                "conditions": [
                    {
                        "path": "/value/predicate",
                        "operator": "eq",
                        "value": "biolink:affects",
                    }
                ],
            },
            {
                "id": "ids",
                "op": "pluck",
                "input": ref("filtered"),
                "path": "/value/object",
                "unique": True,
            },
            {
                "id": "second",
                "op": "query",
                "url": base + "/second",
                "query": query(ref("ids")),
            },
            {
                "id": "right",
                "op": "rows",
                "input": ref("second", "/message/knowledge_graph/edges"),
            },
            {
                "id": "paths",
                "op": "join",
                "left": ref("filtered"),
                "right": ref("right"),
                "left_on": "/value/object",
                "right_on": "/value/subject",
            },
            {
                "id": "summary",
                "op": "project",
                "input": ref("paths"),
                "fields": {
                    "start": "/left/value/subject",
                    "intermediate": "/left/value/object",
                    "end": "/right/value/object",
                },
            },
        ],
        "outputs": {"paths": ref("paths"), "summary": ref("summary")},
    }


def test_two_hop_query_keeps_evidence_and_explains_every_transformation(
    provider, monkeypatch
):
    base, calls = provider
    workflow = recipe(base)
    original = deepcopy(workflow)
    bundle = run_workflow(workflow)
    assert workflow == original
    assert bundle["status"] == "succeeded"
    assert [path for path, _ in calls] == ["/first", "/second"]
    assert calls[0][1] == original["steps"][0]["query"]
    assert calls[1][1]["message"]["query_graph"]["nodes"]["n0"]["ids"] == [
        "EXAMPLE:gene1"
    ]
    assert len(bundle["outputs"]["paths"]) == 2
    assert bundle["steps"]["first"]["output"] == FIRST
    assert bundle["steps"]["first"]["transport"]["status_code"] == 200
    assert bundle["steps"]["filtered"]["removed_count"] == 1
    assert [
        decision["kept"] for decision in bundle["steps"]["filtered"]["decisions"]
    ] == [True, False, True]
    assert bundle["steps"]["edges"]["row_lineage"][0]["inputs"] == [
        {"step": "first", "path": "/message/knowledge_graph/edges/e~1a~01"}
    ]
    assert bundle["steps"]["ids"]["row_lineage"][0]["inputs"] == [
        {"step": "filtered", "path": "/0"},
        {"step": "filtered", "path": "/1"},
    ]
    assert bundle["steps"]["paths"]["unmatched_right"] == [1]
    assert bundle["steps"]["paths"]["row_lineage"][0]["inputs"] == [
        {"step": "filtered", "path": "/0"},
        {"step": "right", "path": "/0"},
    ]

    def no_network(*args, **kwargs):
        raise AssertionError("offline replay contacted a provider")

    monkeypatch.setattr(requests, "post", no_network)
    restored = json.loads(json.dumps(bundle))
    replay = replay_workflow(restored)
    assert replay["outputs"] == bundle["outputs"]
    assert replay["steps"]["first"]["evidence_origin"] == "saved_response"
    assert replay["replayed_from"] == bundle["bundle_sha256"]
    second_replay = replay_workflow(replay)
    assert second_replay["outputs"] == bundle["outputs"]
    assert (
        second_replay["steps"]["first"]["original_started_at"]
        == bundle["steps"]["first"]["started_at"]
    )


def test_live_replay_explicitly_reissues_queries(provider):
    base, calls = provider
    bundle = run_workflow(recipe(base))
    replay = replay_workflow(bundle, mode="live")
    assert len(calls) == 4
    assert replay["rerun_of"] == bundle["bundle_sha256"]
    assert replay["outputs"] == bundle["outputs"]


@pytest.mark.parametrize(
    "path",
    ["fail", "pending", "application-error", "malformed", "bad-json", "redirect"],
)
def test_failures_are_retained_and_dependents_skipped(provider, path):
    base, calls = provider
    workflow = recipe(base)
    workflow["steps"][0]["url"] = f"{base}/{path}"
    workflow["steps"].append({"id": "independent", "op": "literal", "value": [1]})
    bundle = run_workflow(workflow)
    assert len(calls) == 1
    assert bundle["status"] == "incomplete"
    assert bundle["steps"]["first"]["status"] == "failed"
    assert "response_text" in bundle["steps"]["first"]
    assert bundle["steps"]["second"]["status"] == "skipped"
    assert bundle["steps"]["independent"]["status"] == "succeeded"
    assert bundle["output_errors"]
    assert replay_workflow(bundle)["status"] == "incomplete"
    assert len(calls) == 1


def test_empty_result_is_successful_but_empty_ids_never_broaden_query(provider):
    base, calls = provider
    workflow = recipe(base)
    workflow["steps"][0]["url"] = f"{base}/empty"
    bundle = run_workflow(workflow)
    assert len(calls) == 1
    assert bundle["steps"]["first"]["status"] == "succeeded"
    assert bundle["steps"]["first"]["summary"]["result_count"] == 0
    assert bundle["steps"]["ids"]["output"] == []
    assert bundle["steps"]["second"]["status"] == "failed"
    assert "empty upstream selection" in bundle["steps"]["second"]["error"]["message"]
    assert replay_workflow(bundle)["status"] == "incomplete"


def test_timeout_is_not_an_empty_result(monkeypatch):
    def timeout(*args, **kwargs):
        raise requests.Timeout("provider timed out")

    monkeypatch.setattr(requests, "post", timeout)
    bundle = run_workflow(recipe("https://example.invalid"))
    assert bundle["steps"]["first"]["error"]["type"] == "Timeout"
    assert bundle["status"] == "incomplete"
    assert (
        replay_workflow(bundle)["steps"]["first"]["error"]
        == bundle["steps"]["first"]["error"]
    )
    assert (
        replay_workflow(bundle)["steps"]["first"]["evidence_origin"] == "saved_failure"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"message": None},
        {"message": {"query_graph": None}},
        query([None]),
        query([""]),
    ],
)
def test_invalid_dynamic_query_is_recorded_without_network(body, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid query contacted a provider")

    monkeypatch.setattr(requests, "post", forbidden)
    workflow = recipe("https://example.invalid")
    workflow["steps"][0]["query"] = body
    bundle = run_workflow(workflow)
    assert bundle["steps"]["first"]["status"] == "failed"
    assert bundle["status"] == "incomplete"
    assert replay_workflow(bundle)["status"] == "incomplete"


def test_response_size_limit_is_explicit(provider, monkeypatch):
    base, _ = provider
    monkeypatch.setattr(engine, "MAX_RESPONSE_BYTES", 10)
    bundle = run_workflow(recipe(base))
    assert "no complete snapshot" in bundle["steps"]["first"]["error"]["message"]
    assert bundle["status"] == "incomplete"


def test_forward_references_are_sorted_before_execution():
    workflow = {
        "schema_version": 1,
        "steps": [
            {"id": "ids", "op": "pluck", "input": ref("data"), "path": "/id"},
            {"id": "data", "op": "literal", "value": [{"id": "EXAMPLE:1"}]},
        ],
        "outputs": {"ids": ref("ids")},
    }
    assert validate_workflow(workflow)["execution_order"] == ["data", "ids"]
    assert run_workflow(workflow)["outputs"] == {"ids": ["EXAMPLE:1"]}


@pytest.mark.parametrize(
    "change",
    [
        lambda w: w.update(schema_version=2),
        lambda w: w["steps"].append(deepcopy(w["steps"][0])),
        lambda w: w["steps"][2].update(input=ref("missing")),
        lambda w: w["steps"][2].update(input=ref("ids")),
        lambda w: w["steps"][2].update(op="eval"),
        lambda w: w["steps"][2].update(typo=True),
        lambda w: w["steps"][2].update(input=[]),
        lambda w: w["steps"][2]["conditions"][0].update(operator="python"),
        lambda w: w["steps"][2]["conditions"][0].update(path="not-a-pointer"),
        lambda w: w["steps"][0].update(timeout_seconds=0),
        lambda w: w["steps"][0].update(url="file:///etc/passwd"),
        lambda w: w["outputs"].update(paths=ref("paths", "/bad~escape")),
    ],
)
def test_invalid_plans_are_rejected_before_any_query(change, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid recipe contacted a provider")

    monkeypatch.setattr(requests, "post", forbidden)
    workflow = recipe("https://example.invalid")
    change(workflow)
    with pytest.raises(ValueError):
        run_workflow(workflow)


def test_missing_filter_values_are_explained_and_missing_projection_is_failure():
    workflow = {
        "schema_version": 1,
        "steps": [
            {
                "id": "data",
                "op": "literal",
                "value": [{"score": 2}, {}, {"score": "unknown"}],
            },
            {
                "id": "filtered",
                "op": "filter",
                "input": ref("data"),
                "conditions": [{"path": "/score", "operator": "gte", "value": 1}],
            },
            {
                "id": "bad",
                "op": "project",
                "input": ref("data"),
                "fields": {"value": "/absent"},
            },
        ],
        "outputs": {"result": ref("filtered")},
    }
    bundle = run_workflow(workflow)
    assert bundle["outputs"]["result"] == [{"score": 2}]
    assert (
        bundle["steps"]["filtered"]["decisions"][1]["conditions"][0]["basis"]
        == "missing_path"
    )
    assert (
        bundle["steps"]["filtered"]["decisions"][2]["conditions"][0]["basis"]
        == "not_numeric"
    )
    assert bundle["steps"]["bad"]["status"] == "failed"
    assert bundle["status"] == "incomplete"


def test_join_limits_and_null_keys_are_not_silently_truncated(monkeypatch):
    workflow = {
        "schema_version": 1,
        "steps": [
            {"id": "data", "op": "literal", "value": [{"id": "x"}, {"id": "x"}]},
            {
                "id": "joined",
                "op": "join",
                "left": ref("data"),
                "right": ref("data"),
                "left_on": "/id",
                "right_on": "/id",
            },
        ],
        "outputs": {"result": ref("joined")},
    }
    monkeypatch.setattr(engine, "MAX_ROWS", 2)
    result = run_workflow(workflow)
    assert "row limit exceeded" in result["steps"]["joined"]["error"]["message"]
    assert "output" not in result["steps"]["joined"]
    workflow["steps"][0]["value"] = [{"id": None}]
    result = run_workflow(workflow)
    assert "non-null" in result["steps"]["joined"]["error"]["message"]


def test_modified_snapshot_is_rejected():
    workflow = {
        "schema_version": 1,
        "steps": [{"id": "data", "op": "literal", "value": [1]}],
        "outputs": {"result": ref("data")},
    }
    bundle = run_workflow(workflow)
    bundle["steps"]["data"]["output"] = [2]
    with pytest.raises(ValueError, match="checksum"):
        replay_workflow(bundle)


def test_missing_named_output_path_is_incomplete():
    workflow = {
        "schema_version": 1,
        "steps": [{"id": "data", "op": "literal", "value": {}}],
        "outputs": {"result": ref("data", "/missing")},
    }
    bundle = run_workflow(workflow)
    assert bundle["status"] == "incomplete"
    assert bundle["outputs"] == {}
    assert "missing path" in bundle["output_errors"]["result"]


def test_cli_workflow_roundtrip(capsys):
    workflow = {
        "schema_version": 1,
        "steps": [{"id": "data", "op": "literal", "value": [1]}],
        "outputs": {"result": ref("data")},
    }
    assert cli.main(["run-query-workflow", "--workflow", json.dumps(workflow)]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert cli.main(["replay-query-workflow", "--bundle", json.dumps(bundle)]) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["outputs"] == {"result": [1]}


def test_documented_offline_example_is_executable():
    path = Path(__file__).parents[1] / "examples/workflows/offline_pathway.json"
    workflow = json.loads(path.read_text())
    bundle = run_workflow(workflow)
    assert bundle["status"] == "succeeded"
    assert bundle["outputs"]["pathways"] == [
        {
            "start": "EXAMPLE:compound",
            "intermediate": "EXAMPLE:gene1",
            "end": "EXAMPLE:condition",
        }
    ]
    assert replay_workflow(bundle)["outputs"] == bundle["outputs"]
