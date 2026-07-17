"""Tests for the experimental developer-friendly API."""

import pandas as pd
import pytest

from TCT import experimental
from TCT.experimental import FinderResult, TranslatorResources
from TCT.translator_node import TranslatorNode


def _node(curie, label="label", types=None):
    return TranslatorNode(
        curie=curie,
        label=label,
        types=types or ["biolink:NamedThing"],
    )


def _resources():
    return TranslatorResources(
        api_names={"fake-api": "https://example.org/query"},
        meta_kg=pd.DataFrame(),
        api_predicates={"fake-api": ["biolink:related_to"]},
    )


def _raw_output():
    return {
        "query_graph": {"nodes": {}, "edges": {}},
        "knowledge_graph": {"nodes": {"X:1": {}}, "edges": {}},
        "results": [{"analyses": []}],
        "auxiliary_graphs": {},
    }


def test_normalize_category_accepts_short_and_prefixed_names():
    assert experimental._normalize_category("Gene") == "biolink:Gene"
    assert experimental._normalize_category("biolink:Disease") == "biolink:Disease"
    assert experimental._normalize_categories([" Drug "]) == ["biolink:Drug"]
    assert experimental._normalize_categories(None) is None


def test_translator_resources_cache_lifecycle(monkeypatch):
    calls = []

    def fake_fetch():
        calls.append(len(calls))
        return {"api": "url"}, pd.DataFrame({"call": [len(calls)]}), {"api": []}

    monkeypatch.setattr(
        experimental.translator_query,
        "get_translator_API_predicates",
        fake_fetch,
    )
    experimental.clear_translator_resource_cache()

    first = experimental.get_translator_resources()
    second = experimental.get_translator_resources()
    refreshed = experimental.get_translator_resources(refresh=True)

    assert first is second
    assert refreshed is not first
    assert len(calls) == 2

    experimental.clear_translator_resource_cache()
    assert experimental._DEFAULT_TRANSLATOR_RESOURCES is None


def test_resolve_node_normalizes_curie_without_name_lookup(monkeypatch):
    name_lookup_calls = []

    monkeypatch.setattr(
        experimental.node_normalizer,
        "get_normalized_nodes",
        lambda value, **kwargs: _node(value, "Asthma", ["biolink:Disease"]),
    )
    monkeypatch.setattr(
        experimental.name_resolver,
        "lookup",
        lambda *args, **kwargs: name_lookup_calls.append(args),
    )

    resolved = experimental._resolve_node("MONDO:0004979")

    assert resolved.input_value == "MONDO:0004979"
    assert resolved.curie == "MONDO:0004979"
    assert resolved.label == "Asthma"
    assert resolved.categories == ["biolink:Disease"]
    assert name_lookup_calls == []


def test_resolve_node_uses_name_resolver_for_strings(monkeypatch):
    calls = []

    monkeypatch.setattr(
        experimental.name_resolver,
        "lookup",
        lambda value, **kwargs: _node("MONDO:0004979", value, ["biolink:Disease"]),
    )

    def fake_normalize(value, **kwargs):
        calls.append((value, kwargs))
        return _node(value, "asthma", ["biolink:Disease"])

    monkeypatch.setattr(
        experimental.node_normalizer,
        "get_normalized_nodes",
        fake_normalize,
    )

    resolved = experimental._resolve_node(
        "asthma",
        node_normalizer_kwargs={"conflate": True},
    )

    assert resolved.curie == "MONDO:0004979"
    assert resolved.label == "asthma"
    assert calls == [("MONDO:0004979", {"conflate": True})]


def test_resolve_node_raises_for_unknown_curie(monkeypatch):
    monkeypatch.setattr(
        experimental.node_normalizer,
        "get_normalized_nodes",
        lambda value, **kwargs: None,
    )

    with pytest.raises(LookupError, match="Could not normalize CURIE"):
        experimental._resolve_node("DOESNOT:EXIST")


def test_get_resources_uses_complete_resources_and_partial_overrides(monkeypatch):
    monkeypatch.setattr(
        experimental,
        "get_translator_resources",
        lambda: pytest.fail("cache should not be used when resources are provided"),
    )
    base = _resources()
    override_meta = pd.DataFrame({"Subject": ["biolink:Disease"]})

    resolved = experimental._get_resources(resources=base, meta_kg=override_meta)

    assert resolved.api_names is base.api_names
    assert resolved.api_predicates is base.api_predicates
    assert resolved.meta_kg is override_meta


def test_finder_result_to_dict_returns_raw_output():
    raw = _raw_output()
    result = FinderResult(
        query={},
        knowledge_graph={},
        results=[],
        auxiliary_graphs={},
        resolved_nodes={},
        raw=raw,
    )

    assert result.to_dict() is raw


def test_pathfinder_resolves_inputs_queries_apis_and_wraps_output(monkeypatch):
    queries = []

    monkeypatch.setattr(
        experimental,
        "_resolve_node",
        lambda value, **kwargs: _node(
            value if ":" in value else f"CURIE:{value}",
            value,
            ["biolink:Disease"],
        ),
    )
    monkeypatch.setattr(
        experimental,
        "sele_predicates_API",
        lambda source, target, meta_kg, api_names: (
            ["biolink:related_to"],
            ["fake-api"],
            ["https://example.org/query"],
        ),
    )

    def fake_parallel(query_json, select_APIs, APInames, API_predicates, max_workers):
        queries.append((query_json, select_APIs, max_workers))
        return {f"edge-{len(queries)}": {"subject": "s", "object": "o"}}

    monkeypatch.setattr(
        experimental.translator_query, "parallel_api_query", fake_parallel
    )
    monkeypatch.setattr(
        experimental,
        "parse_results_for_pathfinder",
        lambda *args, **kwargs: _raw_output(),
    )

    result = experimental.pathfinder(
        "asthma",
        "albuterol",
        ["Gene"],
        resources=_resources(),
    )

    assert isinstance(result, FinderResult)
    assert result.resolved_nodes["start"].curie == "CURIE:asthma"
    assert result.resolved_nodes["end"].curie == "CURIE:albuterol"
    assert result.knowledge_graph == {"nodes": {"X:1": {}}, "edges": {}}
    assert len(queries) == 2
    assert queries[0][0]["message"]["query_graph"]["nodes"]["n00"]["ids"] == [
        "CURIE:asthma"
    ]
    assert queries[1][0]["message"]["query_graph"]["nodes"]["n01"]["ids"] == [
        "CURIE:albuterol"
    ]
    assert queries[0][1] == ["fake-api"]
    assert queries[0][2] == 1


def test_neighborhood_finder_single_input_queries_and_wraps_output(monkeypatch):
    queries = []

    monkeypatch.setattr(
        experimental,
        "_resolve_nodes",
        lambda values, **kwargs: [
            _node("MONDO:0004979", "asthma", ["biolink:Disease"])
        ],
    )
    monkeypatch.setattr(
        experimental,
        "sele_predicates_API",
        lambda source, target, meta_kg, api_names: (
            ["biolink:treats"],
            ["fake-api"],
            ["https://example.org/query"],
        ),
    )

    def fake_parallel(query_json, select_APIs, APInames, API_predicates, max_workers):
        queries.append(query_json)
        return {"edge-1": {"subject": "MONDO:0004979", "object": "CHEBI:1"}}

    monkeypatch.setattr(
        experimental.translator_query, "parallel_api_query", fake_parallel
    )
    monkeypatch.setattr(
        experimental,
        "parse_results_for_neighborhood_finder",
        lambda *args, **kwargs: _raw_output(),
    )

    result = experimental.neighborhood_finder(
        "asthma",
        ["Drug"],
        resources=_resources(),
        predicates_subset=["biolink:treats"],
    )

    query_graph = queries[0]["message"]["query_graph"]
    assert result.resolved_nodes["node"].curie == "MONDO:0004979"
    assert query_graph["nodes"]["n00"]["ids"] == ["MONDO:0004979"]
    assert query_graph["nodes"]["n01"]["categories"] == ["biolink:Drug"]
    assert query_graph["edges"]["e00"]["predicates"] == ["biolink:treats"]


def test_neighborhood_finder_multiple_inputs_uses_multiple_parser(monkeypatch):
    parser_calls = []

    monkeypatch.setattr(
        experimental,
        "_resolve_nodes",
        lambda values, **kwargs: [
            _node("MONDO:1", "one", ["biolink:Disease"]),
            _node("MONDO:2", "two", ["biolink:Disease"]),
        ],
    )
    monkeypatch.setattr(
        experimental,
        "sele_predicates_API",
        lambda source, target, meta_kg, api_names: ([], ["fake-api"], []),
    )
    monkeypatch.setattr(
        experimental.translator_query,
        "parallel_api_query",
        lambda **kwargs: {},
    )

    def fake_parser(*args, **kwargs):
        parser_calls.append(args)
        return _raw_output()

    monkeypatch.setattr(
        experimental,
        "parse_results_for_neighborhood_finder_multiple_inputs",
        fake_parser,
    )

    result = experimental.neighborhood_finder(
        ["one", "two"],
        ["Gene"],
        resources=_resources(),
    )

    assert list(result.resolved_nodes) == ["node_0", "node_1"]
    assert parser_calls[0][0] == ["MONDO:1", "MONDO:2"]
    assert parser_calls[0][2] == ["biolink:Disease"]
    assert parser_calls[0][3] == ["biolink:Gene"]
