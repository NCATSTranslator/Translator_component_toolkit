"""Offline Phase 4 acceptance, including the single original NLQ fixture."""

import asyncio
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sqlite3

import pytest
import requests

from TCT.evidence import (
    accumulate,
    canonical,
    digest,
    evidence,
    EvidenceError,
    inventory,
    read_run,
    reduce_evidence,
)
from TCT.execution import execution
from TCT.interfaces import tools
from TCT.interfaces.serialization import to_jsonable
from TCT.trapi_validation import validate

FIXTURES = Path(__file__).parent / "fixtures" / "rollup"


def load(name):
    return json.loads((FIXTURES / (name + ".json")).read_text())


@pytest.fixture
def captured(monkeypatch, tmp_path):
    calls = []
    from TCT.config import service_url

    providers = load("providers")

    def frozen(session, method, url, **kw):
        calls.append((method, url, deepcopy(kw)))
        if method.lower() == "get" and url == service_url("smartapi_registry"):
            body = load("registry")
        elif method.lower() == "get" and url.endswith("/get_normalized_nodes"):
            assert kw["params"]["curie"] == "MONDO:0004975"
            body = load("normalization")
        elif method.lower() == "post" and url in providers.values():
            which = "genes" if url == providers["gene-provider"] else "chemicals"
            assert kw["json"] == load("case")["queries"][which]
            body = load("gene" if which == "genes" else "chemical")
        else:
            raise AssertionError(f"Unexpected service request {method} {url}")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        return response

    monkeypatch.setattr(requests.sessions.Session, "request", frozen)
    with execution(
        {"record": True, "trapi": True, "store": str(tmp_path), "langfuse": False}
    ) as run:
        normalization = tools.normalize_nodes(
            "MONDO:0004975", return_equivalent_identifiers=True
        )
        registry = tools.get_kp_info()
        genes = tools.query_knowledge_provider(
            "gene-provider",
            load("case")["queries"]["genes"],
            registry[1],
            load("predicates"),
        )
        chemicals = tools.query_knowledge_provider(
            "chemical-provider",
            load("case")["queries"]["chemicals"],
            registry[1],
            load("predicates"),
        )
    assert len(calls) == 4
    for actual, golden in zip(
        [normalization, registry, genes, chemicals],
        load("golden")["history"],
        strict=False,
    ):
        assert to_jsonable(actual) == golden["output"]
    records = read_run(tmp_path, run.run_id)
    assert accumulate(run) == records
    # No replay/export operation may contact any service.
    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        lambda *a, **kw: pytest.fail("replay performed network I/O"),
    )
    return records, load("composition"), tmp_path, run.run_id


def test_single_nlq_valid_rollup_and_lineage(captured):
    events, composition, _, _ = captured
    report = reduce_evidence(events, composition)
    assert report["status"] == "valid", report
    response = report["draft"]
    assert validate(response)["valid"]
    assert response["message"]["query_graph"] == composition["query_graph"]
    (result,) = response["message"]["results"]
    assert {k: v[0]["id"] for k, v in result["node_bindings"].items()} == {
        "chemical": "EXAMPLE:chemical1",
        "gene": "EXAMPLE:gene1",
        "disease": "MONDO:0004975",
    }
    assert {
        x for origin in result["x-tct-evidence"] for x in origin["original_ids"]
    } == {"a1", "b1"}
    assert result["x-tct-selection-rows"] == [0]
    assert (
        len(response["message"]["knowledge_graph"]["edges"]) == 5
    )  # Includes all three distractors.
    trace = response["x-tct"]["transformations"]
    assert any(step["op"] == "join" and step["row_lineage"] for step in trace.values())
    assert any(step["op"] == "filter" and step["decisions"] for step in trace.values())
    assert all(response["x-tct"]["structural_additions"].values())
    assert report["rollup_hash"] == digest(response)
    assert report["rollup_hash"] == load("rollup-golden")["rollup_hash"]
    assert sorted(report["references"]) == load("rollup-golden")["source_ids"]
    assert not any(
        k in canonical(response)
        for k in ["started_at", "finished_at", "duration_seconds"]
    )
    assert (
        evidence({"action": "export", "events": events, "composition": composition})
        == response
    )


def test_accumulation_algebra_and_shuffled_completion(captured):
    events, composition, _, _ = captured
    a, b, c = events[:3], events[3:6], events[6:]
    assert accumulate(accumulate(a, b), c) == accumulate(a, accumulate(b, c))
    assert accumulate(a, b) == accumulate(b, a)
    assert accumulate(events, events) == accumulate(events)
    expected = reduce_evidence(events, composition)
    for seed in range(8):
        shuffled = deepcopy(events + events)
        random.Random(seed).shuffle(shuffled)
        assert reduce_evidence(shuffled, composition) == expected
    # Dictionary insertion order is representation only, even for duplicate events.
    backwards = json.loads(
        json.dumps(events, sort_keys=True),
        object_pairs_hook=lambda pairs: dict(reversed(pairs)),
    )
    assert reduce_evidence(events + backwards, composition) == expected


def test_conflicting_event_identity_is_rejected(captured):
    events, _, _, _ = captured
    changed = deepcopy(events[0])
    changed["status"] = "failed"
    with pytest.raises(EvidenceError, match="Conflicting"):
        accumulate(events, [changed])


@pytest.mark.parametrize(
    "mutation,phrase",
    [
        (lambda c: c.update(closed=False), "closed=true"),
        (lambda c: c["sources"].update({"source:missing": {}}), "Missing closed input"),
        (
            lambda c: c["query_graph"]["edges"]["affects"].update(
                subject="gene", object="chemical"
            ),
            "direction",
        ),
        (
            lambda c: c["query_graph"]["edges"]["affects"].update(
                knowledge_type="inferred"
            ),
            "inference",
        ),
        (
            lambda c: c["query_graph"]["edges"]["affects"].update(
                attribute_constraints=[{}]
            ),
            "constraint",
        ),
        (
            lambda c: c["workflow"]["steps"].append(
                {"id": "bad", "op": "query", "url": "https://invalid", "query": {}}
            ),
            "network",
        ),
        (lambda c: c["selection"]["edges"]["affects"].update(path="/gene_edge"), "b1"),
        (lambda c: c["selection"]["nodes"].update(disease="/chemical"), "identifier"),
    ],
)
def test_invalid_compositions_cannot_be_exported(captured, mutation, phrase):
    events, composition, _, _ = captured
    mutation(composition)
    report = evidence(
        {"action": "replay", "events": events, "composition": composition}
    )
    assert report["status"] == "invalid"
    assert phrase in str(report), report
    with pytest.raises(EvidenceError, match="export rejected"):
        evidence({"action": "export", "events": events, "composition": composition})


def test_pending_closed_inputs_and_unsupported_final_version(captured):
    events, composition, _, _ = captured
    events.append(
        {
            "format_version": 1,
            "run_id": "pending",
            "call_id": "pending",
            "status": "running",
        }
    )
    assert "still running" in reduce_evidence(events, composition)["error"]
    assert (
        "final TRAPI 2.0.0"
        in reduce_evidence(events[:-1], composition, "2.0.0")["error"]
    )


def test_journal_read_checks_hashes_and_does_not_create(tmp_path, captured):
    events, composition, store, run_id = captured
    assert evidence({"store": str(store), "run_id": run_id})["event_count"] == len(
        events
    )
    assert (
        evidence(
            {
                "action": "export",
                "store": str(store),
                "run_id": run_id,
                "composition": composition,
            }
        )
        == reduce_evidence(events, composition)["draft"]
    )
    nonexistent = tmp_path / "absent"
    with pytest.raises(EvidenceError):
        read_run(nonexistent, "missing")
    assert not nonexistent.exists()
    with sqlite3.connect(store / "journal.sqlite3") as db:
        checksum = db.execute("SELECT event_hash FROM calls LIMIT 1").fetchone()[0]
    (store / "artifacts" / checksum).write_text("{}")
    with pytest.raises(EvidenceError, match="checksum"):
        read_run(store, run_id)


def event(body, query, id="one"):
    return {
        "format_version": 1,
        "run_id": "fixture",
        "call_id": id,
        "status": "succeeded",
        "observations": [
            {
                "kind": "service",
                "status": "received",
                "status_code": 200,
                "request": {
                    "url": "https://fixture.invalid/" + id,
                    "arguments": {"json": {"message": {"query_graph": query}}},
                },
                "body_json": {"message": body},
            }
        ],
    }


def collision_case():
    query = {
        "nodes": {
            "a": {"categories": ["biolink:Gene"]},
            "b": {"categories": ["biolink:Gene"]},
        },
        "edges": {
            "e": {"subject": "a", "object": "b", "predicates": ["biolink:related_to"]}
        },
    }
    body = {
        "knowledge_graph": {
            "nodes": {
                "X:1": {"categories": ["biolink:Gene"], "name": "one"},
                "X:2": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "same": {
                    "subject": "X:1",
                    "object": "X:2",
                    "predicate": "biolink:related_to",
                    "sources": [
                        {
                            "resource_id": "infores:fixture",
                            "resource_role": "primary_knowledge_source",
                        }
                    ],
                    "qualifiers": [
                        {
                            "qualifier_type_id": "biolink:object_aspect_qualifier",
                            "qualifier_value": "activity",
                        }
                    ],
                    "attributes": [
                        {
                            "attribute_type_id": "biolink:support_graphs",
                            "value": ["same"],
                        }
                    ],
                }
            },
        },
        "auxiliary_graphs": {"same": {"edges": ["same"]}},
        "results": [
            {
                "node_bindings": {
                    "a": [{"id": "X:1", "query_id": "X:1"}],
                    "b": [{"id": "X:2"}],
                },
                "analyses": [
                    {
                        "resource_id": "infores:fixture",
                        "score": 0.7,
                        "scoring_method": "fixture",
                        "edge_bindings": {"e": [{"id": "same"}]},
                        "support_graphs": ["same"],
                    }
                ],
            }
        ],
    }
    first = event(body, query)
    other = deepcopy(body)
    other["knowledge_graph"]["nodes"]["X:1"]["name"] = "alternate"
    other["knowledge_graph"]["edges"]["same"]["sources"][0]["resource_id"] = (
        "infores:other"
    )
    second = event(other, query, "two")
    events = [first, second]
    sources, _, _ = inventory(events)
    ids = sorted(sources)
    composition = {
        "closed": True,
        "query_graph": query,
        "sources": {
            key: {"nodes": {"a": "a", "b": "b"}, "edges": {"e": "e"}} for key in ids
        },
        "workflow": {
            "schema_version": 1,
            "steps": [
                {
                    "id": "answers",
                    "op": "literal",
                    "value": [{"a": "X:1", "b": "X:2", "edge": "same"}],
                }
            ],
            "outputs": {"answers": {"$ref": "answers"}},
        },
        "selection": {
            "output": "answers",
            "resource_id": "infores:tct",
            "nodes": {"a": "/a", "b": "/b"},
            "edges": {"e": {"source_id": ids[0], "path": "/edge"}},
        },
    }
    return events, composition


def test_identifier_collisions_preserve_qualifiers_analyses_and_support():
    events, composition = collision_case()
    report = reduce_evidence(events, composition)
    assert report["status"] == "valid", report
    response = report["draft"]
    message = response["message"]
    assert (
        len(message["knowledge_graph"]["edges"])
        == len(message["auxiliary_graphs"])
        == 2
    )
    assert len(response["x-tct"]["node_variants"]["X:1"]) == 2
    for source_id, refs in report["references"].items():
        edge = message["knowledge_graph"]["edges"][refs["edges"]["same"]]
        assert edge["qualifiers"][0]["qualifier_value"] == "activity"
        assert edge["attributes"][0]["value"] == [refs["auxiliary_graphs"]["same"]]
        analysis = response["x-tct"]["source_results"][source_id][0]["analyses"][0]
        assert analysis["score"] == 0.7 and analysis["scoring_method"] == "fixture"
        assert analysis["support_graphs"] == [refs["auxiliary_graphs"]["same"]]
        assert analysis["edge_bindings"]["e"][0]["id"] == refs["edges"]["same"]
        assert message["auxiliary_graphs"][refs["auxiliary_graphs"]["same"]][
            "edges"
        ] == [refs["edges"]["same"]]
    assert reduce_evidence(list(reversed(events)), composition) == report


def test_invalid_reference_and_schema_errors_are_explicit():
    events, composition = collision_case()
    events[0]["observations"][0]["body_json"]["message"]["knowledge_graph"]["edges"][
        "same"
    ]["sources"] = []
    # Changed response identity must be remapped deliberately, never matched heuristically.
    assert reduce_evidence(events, composition)["status"] == "invalid"
    assert not validate(
        {
            "message": {
                "knowledge_graph": {"nodes": {"X:1": {}}, "edges": {}},
                "results": [],
            }
        }
    )["valid"]


def test_beta_path_native_schema_and_unsupported_conversion():
    query = {
        "nodes": {
            "a": {"categories": ["biolink:Gene"]},
            "b": {"categories": ["biolink:Gene"]},
        },
        "paths": {"p": {"subject": "a", "object": "b"}},
    }
    body = {
        "knowledge_graph": {
            "nodes": {
                "X:1": {"categories": ["biolink:Gene"]},
                "X:2": {"categories": ["biolink:Gene"]},
            },
            "edges": {
                "e": {
                    "subject": "X:1",
                    "object": "X:2",
                    "predicate": "biolink:related_to",
                    "sources": [
                        {
                            "resource_id": "infores:fixture",
                            "resource_role": "primary_knowledge_source",
                        }
                    ],
                    "knowledge_level": "knowledge_assertion",
                    "agent_type": "manual_agent",
                }
            },
        },
        "auxiliary_graphs": {"p": {"edges": ["e"]}},
        "results": [
            {
                "node_bindings": {"a": {"ids": ["X:1"]}, "b": {"ids": ["X:2"]}},
                "analyses": [
                    {
                        "resource_id": "infores:fixture",
                        "path_bindings": {"p": {"ids": ["p"]}},
                    }
                ],
            }
        ],
    }
    events = [event(body, query)]
    source_id = next(iter(inventory(events)[0]))
    composition = {
        "closed": True,
        "query_graph": query,
        "sources": {
            source_id: {"nodes": {"a": "a", "b": "b"}, "edges": {}, "paths": {"p": "p"}}
        },
        "workflow": {
            "schema_version": 1,
            "steps": [
                {
                    "id": "answer",
                    "op": "literal",
                    "value": [{"a": "X:1", "b": "X:2", "path": "p"}],
                }
            ],
            "outputs": {"answer": {"$ref": "answer"}},
        },
        "selection": {
            "output": "answer",
            "resource_id": "infores:tct",
            "nodes": {"a": "/a", "b": "/b"},
            "edges": {},
            "paths": {"p": {"source_id": source_id, "path": "/path"}},
        },
    }
    report = reduce_evidence(events, composition, "2.0.0-beta2")
    assert report["status"] == "valid", report
    assert report["validation"]["schema"]["prerelease"] is True
    assert report["draft"]["schema_version"] == "2.0.0-beta2"
    assert reduce_evidence(events, composition, "1.5.0")["status"] == "invalid"
    assert reduce_evidence(events, composition, "2.0.0")["status"] == "invalid"


def test_cli_mcp_and_native_evidence_are_equivalent(captured, capsys):
    from TCT.interfaces.cli import main
    from TCT.interfaces.mcp import mcp

    events, composition, store, run_id = captured
    capsys.readouterr()
    request = {
        "action": "export",
        "store": str(store),
        "run_id": run_id,
        "composition": composition,
    }
    native = tools.evidence(request)
    assert main(["evidence", "--request", json.dumps(request)]) == 0
    assert json.loads(capsys.readouterr().out) == native

    async def call():
        registered = await mcp.get_tool("evidence")
        result = await registered.run({"request": request})
        return result.structured_content

    assert asyncio.run(call()) == native


def test_pins_have_matching_digests():
    root = Path(__file__).parents[1] / "TCT" / "schemas"
    for version, pin in json.loads((root / "manifest.json").read_text()).items():
        assert (
            hashlib.sha256((root / f"trapi-{version}.yaml").read_bytes()).hexdigest()
            == pin["sha256"]
        )


def test_export_can_be_recorded_in_the_same_run(captured):
    events, composition, store, run_id = captured
    request = {
        "action": "export",
        "store": str(store),
        "run_id": run_id,
        "composition": composition,
    }
    baseline = tools.evidence(request)
    with execution(
        {"record": True, "store": str(store), "run_id": run_id, "langfuse": False}
    ) as run:
        assert tools.evidence(request) == baseline
    assert run[0]["status"] == "succeeded"
    assert read_run(store, run_id)


def test_dependency_order_is_explicit_and_unknown_rank_is_rejected(captured):
    events, composition, _, _ = captured
    baseline = reduce_evidence(events, composition)
    reordered = deepcopy(composition)
    reordered["workflow"]["steps"].reverse()
    result = reduce_evidence(events, reordered)
    assert result["status"] == "valid"
    assert result["draft"]["message"] == baseline["draft"]["message"]
    assert (
        result["draft"]["x-tct"]["transformations"]
        == baseline["draft"]["x-tct"]["transformations"]
    )
    composition["rank"] = "best"
    assert "ranking" in reduce_evidence(events, composition)["error"]


def test_missing_recorded_input_and_invalid_source_report(captured):
    events, composition, _, _ = captured
    source_event = next(e for e in events if e.get("operation") == "query_KP")
    assert (
        "Missing closed input"
        in reduce_evidence([e for e in events if e is not source_event], composition)[
            "error"
        ]
    )
    source_event["status"] = "capture_failed"
    assert "did not complete" in reduce_evidence(events, composition)["error"]


def test_offline_external_schema_refs_are_rejected_without_fetch(monkeypatch):
    monkeypatch.setattr(
        requests.sessions.Session,
        "request",
        lambda *a, **kw: pytest.fail("network validation"),
    )
    report = validate({"message": {}, "workflow": [{"id": "lookup"}]})
    assert not report["valid"]
    assert (
        "not vendored" in report["errors"][0]["message"]
        or "Unresolvable" in report["errors"][0]["message"]
    )


def test_sources_from_existing_workflow_evidence_are_reused(captured):
    events, _, _, _ = captured
    source = next(iter(inventory(events)[0].values()))
    record = {
        "format_version": 1,
        "run_id": "workflow",
        "call_id": "workflow",
        "status": "succeeded",
        "output": {
            "schema_version": 1,
            "steps": {
                "q": {
                    "op": "query",
                    "status": "succeeded",
                    "inputs": {"url": source["url"], "query": source["query"]},
                    "transport": {"status_code": 200},
                    "response": source["response"],
                }
            },
        },
    }
    extracted, issues, workflows = inventory([record])
    assert set(extracted) <= set(inventory(events)[0])
    assert not issues and len(workflows) == 1


def test_rollup_is_detached_and_failed_workflow_inputs_are_not_selected(captured):
    events, composition, _, _ = captured
    original_events, original_composition = deepcopy(events), deepcopy(composition)
    report = reduce_evidence(events, composition)
    report["draft"]["x-tct"]["source_mappings"].clear()
    report["draft"]["x-tct"]["recipe"]["steps"].clear()
    assert events == original_events and composition == original_composition
    source = next(iter(inventory(events)[0].values()))
    record = {
        "format_version": 1,
        "run_id": "failed",
        "call_id": "failed",
        "status": "succeeded",
        "output": {
            "schema_version": 1,
            "steps": {
                "query": {
                    "op": "query",
                    "status": "failed",
                    "inputs": {"url": source["url"], "query": source["query"]},
                    "transport": {"status_code": 200},
                    "response": source["response"],
                }
            },
        },
    }
    sources, issues, _ = inventory([record])
    assert not next(iter(sources.values()))["eligible"]
    assert any(issue["status"] == "workflow_step_failed" for issue in issues)


def test_malformed_and_null_provider_body_is_inspectable():
    record = event({"knowledge_graph": None}, {"nodes": {}, "edges": {}})
    assert (
        next(iter(evidence({"events": [record]})["sources"].values()))["node_count"]
        == 0
    )
    record["observations"][0]["body_json"] = {"error": "not a TRAPI response"}
    assert evidence({"events": [record]})["issues"][0]["status"] == "invalid_trapi_body"
