"""Offline acceptance for durable finder evidence and HTTP snapshot replay."""

from collections import Counter
import json

import pytest
import requests

import TCT
from TCT import TCT as core
from TCT import config
from TCT.evidence import evidence, read_run
from TCT.interfaces.serialization import to_jsonable


def test_finder_recording_reads_and_replays_offline(monkeypatch, tmp_path):
    metformin = "CHEBI:6801"
    provider_urls = {
        name: f"https://{name}.fixture.invalid" for name in ("answer", "empty", "error")
    }
    query_urls = {name: f"{url}/query" for name, url in provider_urls.items()}
    registry = {
        "hits": [
            {
                "_id": name,
                "info": {"title": name},
                "servers": [{"url": url, "x-maturity": "staging"}],
            }
            for name, url in provider_urls.items()
        ]
    }
    # The unrelated predicates make the table large without increasing query fan-out.
    meta_kg = {"hits": [{"_id": "Drug-treats-Disease"}]}
    meta_kg["hits"].extend(
        {"_id": f"Gene-fixture_predicate_{index}-Gene"} for index in range(1000)
    )
    plover_meta_kg = {
        "edges": [
            {
                "subject": "biolink:Gene",
                "predicate": "biolink:affects",
                "object": "biolink:Gene",
            }
        ]
        * 12
    }
    fixture_edges = {
        f"fixture-edge-{index}": {
            "subject": metformin,
            "predicate": "biolink:treats",
            "object": f"FIXTURE:Disease{index}",
            "sources": [
                {
                    "resource_id": "infores:fixture",
                    "resource_role": "primary_knowledge_source",
                }
            ],
            "attributes": [
                {"attribute_type_id": "object_category", "value": "biolink:Disease"},
                {
                    "attribute_type_id": "object_name",
                    "value": f"Synthetic disease {index}",
                },
                {
                    "attribute_type_id": "biolink:description",
                    "value": "Synthetic evidence. " * 30,
                },
            ],
        }
        for index in range(256)
    }

    monkeypatch.setattr(
        config, "_configured_runtime", config.RuntimeConfig(environment="ci")
    )
    monkeypatch.setattr(core, "_DEFAULT_TRANSLATOR_RESOURCES", None)
    calls = []

    def transport(session, method, url, **kwargs):
        calls.append((method, url))
        status = 200
        if url == config.service_url("smartapi_registry"):
            body = registry
        elif url.startswith("https://smart-api.info/api/metakg?"):
            body = meta_kg
        elif url.endswith("/meta_knowledge_graph"):
            body = plover_meta_kg
        elif url.endswith("/lookup"):
            assert kwargs["params"]["string"] == "metformin"
            body = [{"curie": metformin, "names": ["Metformin"], "types": ["Drug"]}]
        elif url.endswith("/get_normalized_nodes"):
            assert kwargs["params"]["curie"] == metformin
            body = {
                metformin: {
                    "id": {"identifier": metformin, "label": "Metformin"},
                    "type": ["biolink:Drug"],
                }
            }
        elif url in query_urls.values():
            graph = kwargs["json"]["message"]["query_graph"]
            assert graph["nodes"]["n00"]["ids"] == [metformin]
            assert graph["edges"]["e00"]["predicates"] == ["biolink:treats"]
            edges = fixture_edges if url == query_urls["answer"] else {}
            body = {"message": {"knowledge_graph": {"nodes": {}, "edges": edges}}}
            if url == query_urls["error"]:
                status = 503
        else:
            pytest.fail(f"Unexpected HTTP request: {method} {url}")
        response = requests.Response()
        response.url = url
        response.status_code = status
        response._content = json.dumps(body).encode()
        return response

    monkeypatch.setattr(requests.Session, "request", transport)
    settings = {"store": str(tmp_path), "record": True, "langfuse": False}

    def find():
        return TCT.neighborhood_finder(
            "metformin", ["Disease"], predicates_subset=["biolink:treats"]
        )

    with TCT.execution(settings | {"run_id": "source", "cache": True}) as source:
        original = find()
    assert len(calls) == 16
    assert original.resolved_nodes["node"].curie == metformin
    assert original.knowledge_graph["edges"] == fixture_edges
    recorded_bytes = sum(
        file.stat().st_size for file in tmp_path.rglob("*") if file.is_file()
    )
    assert recorded_bytes < 50_000_000

    def no_http(*args, **kwargs):
        pytest.fail("Reading evidence or replaying the finder performed HTTP")

    monkeypatch.setattr(requests.Session, "request", no_http)
    TCT.clear_translator_resource_cache()
    with TCT.execution(
        settings
        | {
            "run_id": "replay",
            "cache": {"mode": "replay", "snapshot_run": source.run_id},
        }
    ) as replay:
        assert find() == original
    assert len(replay.cache_events) == len(calls)
    assert all(item["outcome"] == "replayed" for item in replay.cache_events)

    for run in (source, replay):
        records = read_run(tmp_path, run.run_id)
        (finder,) = [
            event
            for event in records
            if event.get("operation") == "neighborhood_finder"
        ]
        assert finder["output"] == to_jsonable(original)
        request = {"action": "export", "store": str(tmp_path), "run_id": run.run_id}
        trace = evidence(request | {"view": "trace"})
        assert trace["call_count"] == len(records)
        assert any(
            call["parent_call_id"] == finder["call_id"] for call in trace["calls"]
        )

        providers = evidence(request | {"view": "providers"})
        assert providers["request_count"] == len(calls)
        assert Counter(
            item["outcome"]
            for service in providers["services"]
            if service["url"].endswith("/query")
            for item in service["requests"]
        ) == {"answered": 1, "empty": 1, "http_error": 1}

        (merge,) = evidence(request | {"view": "edges"})["merges"]
        assert merge["edges"].keys() == fixture_edges.keys()
        assert all(
            edge["retained_provider"] == "answer" for edge in merge["edges"].values()
        )
        report = evidence(request | {"view": "page"})["html"]
        assert "Merged edge provenance" in report
        assert "fixture-edge-255" in report
        assert query_urls["error"] in report
        assert "http_error" in report
        assert "infores:fixture" in report

    assert evidence(
        {
            "action": "export",
            "view": "diff",
            "store": str(tmp_path),
            "run_id": replay.run_id,
            "against": {"store": str(tmp_path), "run_id": source.run_id},
        }
    ) == {"edge_changes": [], "request_changes": []}
