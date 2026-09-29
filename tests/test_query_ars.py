"""Offline tests for the ARS client and its finder APIs (TCT.Query_ARS).

The uploaded-JSON and notebook-parity cases come from ``feat/ars-query-support``
(Guangrong Qin); the fixtures and merge-aware polling cases are adapted from
``feat/ars-client`` (Frankie Hodges).
"""

from __future__ import annotations

import importlib

import pytest

ars = importlib.import_module("TCT.Query_ARS")
from TCT import ARS_neighborhood_finder, ARS_pathfinder  # noqa: E402
from TCT.TCT import FinderResult, ResolvedNode  # noqa: E402
from tests.ars_fixtures import (  # noqa: E402
    BASE,
    MERGED,
    PARENT,
    FakeResponse,
    child,
    done_trace,
    envelope,
    merged_message,
    trace,
)


@pytest.fixture
def no_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(ars.time, "sleep", lambda seconds: calls.append(seconds))
    return calls


def _resolved(values):
    """ResolvedNode stand-ins keyed to the input order."""
    return [
        ResolvedNode(
            input_value=value,
            curie=f"MONDO:{index}",
            label=value,
            categories=["biolink:Disease"],
        )
        for index, value in enumerate([values] if isinstance(values, str) else values)
    ]


# --------------------------------------------------------------------------- #
# query construction
# --------------------------------------------------------------------------- #
def test_one_hop_input_matches_notebook_query(monkeypatch):
    captured = {}

    def fake_query(query_json, *, url=None):
        captured.setdefault("query", query_json)
        return PARENT

    status = ars.parse_trace(PARENT, done_trace())
    message = merged_message()
    monkeypatch.setattr(ars, "submit_ARS", fake_query)
    monkeypatch.setattr(ars, "wait_for_ARS", lambda pk, **kwargs: status)
    monkeypatch.setattr(
        ars, "fetch_ars_results", lambda pk, *, url=None: envelope(message)
    )

    result = ARS_neighborhood_finder("MONDO:0005148", ["biolink:Drug"])

    assert captured["query"] == {
        "message": {"query_graph": {
            "edges": {"e00": {"subject": "n00", "object": "n01", "predicates": ["biolink:related_to"]}},
            "nodes": {"n00": {"ids": ["MONDO:0005148"]}, "n01": {"categories": ["biolink:Drug"]}},
        }},
        "submitter": "TCT",
    }
    assert result.pk == PARENT
    assert result.merged_pk == MERGED
    assert result.resolved_nodes["node"].curie == "MONDO:0005148"


def test_pathfinder_query_uses_shared_query_graph_builder(monkeypatch):
    graph = {"nodes": {"sn": {}, "on": {}}, "paths": {"p0": {}}}
    calls = []

    def build_query_graph(**kwargs):
        calls.append(kwargs)
        return graph

    monkeypatch.setattr(ars, "build_query_graph", build_query_graph)

    query = ars.format_query_json_forARS_pathfinder(
        "PUBCHEM.COMPOUND:132212657",
        "MONDO:0018874",
        ["biolink:SmallMolecule"],
        ["biolink:Disease"],
        [{"intermediate_categories": ["biolink:Gene"]}],
    )

    assert query == {
        "message": {"query_graph": graph},
        "submitter": "TCT",
    }
    assert calls == [{
        "start_node_id": "PUBCHEM.COMPOUND:132212657",
        "end_node_id": "MONDO:0018874",
        "start_node_categories": ["biolink:SmallMolecule"],
        "end_node_categories": ["biolink:Disease"],
        "constraints_path": [{"intermediate_categories": ["biolink:Gene"]}],
    }]


def test_pathfinder_query_requires_both_endpoint_curies():
    with pytest.raises(ValueError, match="start_node_id and end_node_id"):
        ars.format_query_json_forARS_pathfinder("", "MONDO:0018874")


def test_pathfinder_resolves_and_keys_resolved_nodes(monkeypatch):
    submitted = {}
    status = ars.parse_trace(PARENT, done_trace())
    message = merged_message()

    monkeypatch.setattr(
        ars, "_resolve_nodes", lambda values, **kwargs: _resolved(values)
    )

    def fake_query(query_json, *, url=None):
        submitted.update(query_json)
        return PARENT

    monkeypatch.setattr(ars, "submit_ARS", fake_query)
    monkeypatch.setattr(ars, "wait_for_ARS", lambda pk, **kwargs: status)
    monkeypatch.setattr(ars, "fetch_ars_results", lambda pk, *, url=None: envelope(message))

    result = ARS_pathfinder(
        "asthma",
        "albuterol",
        intermediate_categories=["Gene", "Protein"],
    )

    graph = submitted["message"]["query_graph"]
    assert graph["nodes"]["sn"]["ids"] == ["MONDO:0"]
    assert graph["nodes"]["on"]["ids"] == ["MONDO:1"]
    # Only the first intermediate category is applied, mirroring the local pathfinder.
    assert graph["paths"]["p0"]["constraints"] == [{"intermediate_categories": ["biolink:Gene"]}]
    assert result.resolved_nodes["start"].curie == "MONDO:0"
    assert result.resolved_nodes["end"].curie == "MONDO:1"


def test_invalid_uploaded_json_is_rejected_before_submission(monkeypatch):
    monkeypatch.setattr(ars, "_post", lambda *args, **kwargs: pytest.fail("unexpected POST"))
    with pytest.raises(ValueError, match="message.query_graph"):
        ARS_neighborhood_finder(json_file={"message": None})


def test_mutually_exclusive_inputs_are_rejected():
    with pytest.raises(ValueError, match="json_file or node"):
        ARS_neighborhood_finder(
            json_file={"message": {"query_graph": {}}},
            node=["MONDO:1"],
            neighbor_categories=["biolink:Drug"],
        )


def test_multi_input_neighborhood_finder_keys_node_index(monkeypatch):
    status = ars.parse_trace(PARENT, done_trace())
    message = merged_message()
    monkeypatch.setattr(ars, "_resolve_nodes", lambda values, **kwargs: _resolved(values))
    monkeypatch.setattr(ars, "submit_ARS", lambda query, *, url=None: PARENT)
    monkeypatch.setattr(ars, "wait_for_ARS", lambda pk, **kwargs: status)
    monkeypatch.setattr(ars, "fetch_ars_results", lambda pk, *, url=None: envelope(message))

    result = ARS_neighborhood_finder(
        ["MONDO:0004979", "MONDO:0004979"], ["biolink:Drug"]
    )

    assert list(result.resolved_nodes) == ["node_0", "node_1"]


# --------------------------------------------------------------------------- #
# submit / fetch / trace parsing
# --------------------------------------------------------------------------- #
def test_submit_uses_configured_ars_url(monkeypatch):
    posted = {}

    def fake_post(url, json_body):
        posted["url"] = url
        posted["json"] = json_body
        return FakeResponse({"pk": PARENT, "fields": {"status": "Running"}}, 201)

    monkeypatch.setattr(ars, "_post", fake_post)

    pk = ars.submit_ARS({"message": {"query_graph": {}}}, url=BASE.rstrip("/"))

    assert pk == PARENT
    assert posted["url"] == BASE + "submit"


def test_submit_rejects_http_failures_and_missing_pk(monkeypatch):
    monkeypatch.setattr(ars, "_post", lambda *a, **k: FakeResponse({"detail": "bad"}, 500))
    with pytest.raises(ars.ARSError, match="HTTP 500"):
        ars.submit_ARS({"message": {"query_graph": {}}})

    monkeypatch.setattr(ars, "_post", lambda *a, **k: FakeResponse({"fields": {}}, 201))
    with pytest.raises(ValueError, match="did not return a message pk"):
        ars.submit_ARS({"message": {"query_graph": {}}})


def test_parse_trace_reads_children_and_merge_state():
    status = ars.parse_trace(PARENT, done_trace())

    assert status.status == "Done"
    assert status.merged_version == MERGED
    assert [c.agent for c in status.children] == ["ars-ars-agent", "ara-shepherd-arax"]
    assert status.merge_child.result_count == 3
    assert status.merged_ready
    assert status.is_terminal
    assert "ars-ars-agent=Done" in status.summary()

    # The ARS serializes merged_versions_list as a Python repr string.
    repr_trace = done_trace()
    repr_trace["merged_versions_list"] = (
        f"[['{MERGED}', 'ars'], ['child', 'ara-shepherd-arax']]"
    )
    parsed = ars.parse_trace(PARENT, repr_trace)
    assert parsed.merged_versions_list == ((MERGED, "ars"), ("child", "ara-shepherd-arax"))
    assert ars.parse_trace(
        PARENT, {**repr_trace, "merged_versions_list": [[MERGED, "ars"]]}
    ).merged_versions_list == ((MERGED, "ars"),)
    assert ars.parse_trace(
        PARENT, {**repr_trace, "merged_versions_list": "not a list"}
    ).merged_versions_list == (("not a list",),)

    running = ars.parse_trace(PARENT, trace("Running"))
    assert not running.is_terminal
    assert not running.merged_ready
    assert running.summary() == "no children yet"


def test_get_message_maps_404(monkeypatch):
    monkeypatch.setattr(ars, "_get", lambda *a, **k: FakeResponse({}, 404))
    with pytest.raises(LookupError):
        ars.get_message("missing")


# --------------------------------------------------------------------------- #
# polling
# --------------------------------------------------------------------------- #
def _poll_sequence(monkeypatch, traces):
    """Serve successive trace responses; the last one repeats."""
    calls = []

    def fake_get(url, params=None):
        index = min(len(calls), len(traces) - 1)
        calls.append(url)
        return FakeResponse(traces[index], 200)

    monkeypatch.setattr(ars, "_get", fake_get)
    return calls


def test_polling_stops_after_limit(monkeypatch, no_sleep):
    _poll_sequence(monkeypatch, [trace("Running")])

    with pytest.raises(TimeoutError):
        ars.check_ars_results("pk", max_retries=2)


def test_wait_returns_once_parent_and_merge_child_are_done(monkeypatch, no_sleep):
    calls = _poll_sequence(
        monkeypatch, [trace("Running"), trace("Running"), done_trace()]
    )

    status = ars.wait_for_ARS(PARENT, poll_interval=1, max_retries=60)

    assert status.merged_version == MERGED
    assert len(calls) == 3
    assert no_sleep == [1, 1]


def test_wait_keeps_polling_when_parent_done_but_merge_child_still_running(monkeypatch, no_sleep):
    # NCATSTranslator/Relay#621: the parent flips to Done before the merged
    # message is saved. The merge child must also be Done before we return.
    calls = _poll_sequence(
        monkeypatch,
        [done_trace(merge_status="Running"), done_trace(merge_status="Running"), done_trace()],
    )

    status = ars.wait_for_ARS(PARENT, poll_interval=1, max_retries=60)

    assert status.merged_ready
    assert len(calls) == 3


def test_wait_returns_after_grace_when_no_merged_message_appears(monkeypatch, no_sleep):
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(ars.time, "monotonic", lambda: next(clock))
    calls = _poll_sequence(
        monkeypatch, [trace("Done", None, [child("ara-x", "Done")])]
    )

    status = ars.wait_for_ARS(
        PARENT, poll_interval=1, max_retries=600, merge_grace=25
    )

    assert status.status == "Done"
    assert status.merged_version is None
    assert len(calls) >= 2  # waited through the grace window, then returned


def test_wait_raises_on_error_status(monkeypatch, no_sleep):
    _poll_sequence(monkeypatch, [trace("Error", None, [child("ara-x", "Error", code=500)])])

    with pytest.raises(ars.ARSError, match="status Error"):
        ars.wait_for_ARS(PARENT, poll_interval=1, max_retries=60)


# --------------------------------------------------------------------------- #
# result collection and summarization
# --------------------------------------------------------------------------- #
def test_results_come_from_merged_message_or_fall_back_to_parent(monkeypatch):
    fetched = []

    def fake_get(url, params=None):
        fetched.append((url, params))
        if params:
            return FakeResponse(done_trace(), 200)
        return FakeResponse(envelope(merged_message()), 200)

    monkeypatch.setattr(ars, "_get", fake_get)

    result = ars.get_ARS_result(PARENT)

    assert result.merged_pk == MERGED
    assert fetched[-1][0].endswith(f"messages/{MERGED}")
    assert len(result.results) == 2
    assert isinstance(result, FinderResult)
    assert result.to_dict() is result.raw
    assert result.summarize(1)[0]["essence"] == "drug"

    status = ars.parse_trace(PARENT, trace("Done", None, []))
    fallback = ars.get_ARS_result(status)
    assert fallback.merged_pk is None
    assert fetched[-1][0].endswith(f"messages/{PARENT}")


def test_pending_result_raises(monkeypatch):
    monkeypatch.setattr(
        ars, "get_ARS_status", lambda pk, url=None: ars.parse_trace(PARENT, trace("Running"))
    )
    with pytest.raises(ars.ARSPendingError):
        ars.get_ARS_result(PARENT)


def test_empty_shell_returned_without_merged_message(monkeypatch):
    status = ars.parse_trace(PARENT, trace("Done", None, [child("ara-x", "Done")]))
    monkeypatch.setattr(ars, "submit_ARS", lambda query, *, url=None: PARENT)
    monkeypatch.setattr(ars, "wait_for_ARS", lambda pk, **kwargs: status)
    monkeypatch.setattr(ars, "fetch_ars_results", lambda pk, *, url=None: {"fields": {"data": {}}})

    result = ARS_neighborhood_finder(json_file={"message": {"query_graph": {}}})

    assert isinstance(result, ars.ARSResult)
    assert result.results == []
    assert result.knowledge_graph == {"nodes": {}, "edges": {}}
    assert result.raw["query_graph"] == {}


def test_summarize_results_flattens_bindings_predicates_and_sources():
    rows = ars.summarize_results(merged_message(), top_n=1)

    assert len(rows) == 1
    row = rows[0]
    assert row["rank"] == 1 and row["score"] == 0.9
    assert row["essence"] == "drug"
    assert row["nodes"]["n1"][0]["name"] == "drug"
    assert row["predicates"] == ["biolink:treats"]
    assert row["primary_sources"] == ["infores:a"]
    assert row["aras"] == ["infores:arax"]
    assert row["edge_count"] == 1

    assert len(ars.summarize_results(merged_message(), top_n=None)) == 2
    assert ars.summarize_results(None) == []
