"""Offline tests for the ARS client (TCT.ars) and its agent-facing tools."""

from __future__ import annotations

import pytest

from TCT import ars
from TCT.interfaces import tools
from TCT.TCT import FinderResult, ResolvedNode
from TCT.translator_node import TranslatorNode


BASE = "https://ars.example.org/ars/api/"
PARENT = "11111111-1111-1111-1111-111111111111"
MERGED = "22222222-2222-2222-2222-222222222222"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def _child(agent, status, pk="child", result_count=None, code=200):
    return {
        "actor": {"agent": agent, "inforesid": f"infores:{agent}"},
        "status": status,
        "code": code,
        "message": pk,
        "result_count": result_count,
    }


def _trace(status, merged=None, children=()):
    return {
        "status": status,
        "code": 200 if status == "Done" else 202,
        "merged_version": merged,
        "merged_versions_list": [],
        "children": list(children),
    }


def _done_trace(merged=MERGED, merge_status="Done"):
    return _trace(
        "Done",
        merged,
        [
            _child(ars.MERGE_AGENT, merge_status, pk=merged, result_count="3"),
            _child("ara-shepherd-arax", "Done", result_count=3),
        ],
    )


def _merged_message():
    return {
        "query_graph": {"nodes": {}, "edges": {}},
        "knowledge_graph": {
            "nodes": {
                "MONDO:1": {"name": "disease", "categories": ["biolink:Disease"]},
                "CHEBI:1": {"name": "drug", "categories": ["biolink:SmallMolecule"]},
            },
            "edges": {
                "e1": {
                    "subject": "CHEBI:1",
                    "object": "MONDO:1",
                    "predicate": "biolink:treats",
                    "sources": [
                        {"resource_role": "primary_knowledge_source", "resource_id": "infores:a"},
                        {"resource_role": "aggregator_knowledge_source", "resource_id": "infores:agg"},
                    ],
                }
            },
        },
        "results": [
            {
                "rank": 1,
                "normalized_score": 0.9,
                "essence": "drug",
                "essence_category": "biolink:SmallMolecule",
                "node_bindings": {"n0": [{"id": "MONDO:1"}], "n1": [{"id": "CHEBI:1"}]},
                "analyses": [
                    {"resource_id": "infores:arax", "edge_bindings": {"e0": [{"id": "e1"}]}}
                ],
            },
            {"rank": 2, "score": 0.1, "node_bindings": {}, "analyses": []},
        ],
        "auxiliary_graphs": {},
    }


def _envelope(message, pk=MERGED):
    return {"model": "tr_ars.message", "pk": pk, "fields": {"status": "Done", "data": {"message": message}}}


@pytest.fixture
def no_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(ars.time, "sleep", lambda s: calls.append(s))
    return calls


# --------------------------------------------------------------------------- #
# submit / get_message / parse_trace
# --------------------------------------------------------------------------- #
def test_submit_wraps_bare_query_graph_and_returns_pk(monkeypatch):
    posted = {}

    def fake_post(url, json, timeout):
        posted["url"] = url
        posted["json"] = json
        return FakeResponse({"pk": PARENT, "fields": {"status": "Running"}}, 201)

    monkeypatch.setattr(ars.requests, "post", fake_post)

    pk = ars.submit({"nodes": {}, "edges": {}}, base_url=BASE)

    assert pk == PARENT
    assert posted["url"] == BASE + "submit"
    assert posted["json"] == {"message": {"query_graph": {"nodes": {}, "edges": {}}}}


def test_submit_uses_configured_ars_url(monkeypatch):
    posted = {}
    monkeypatch.setattr(ars, "service_url", lambda name: {"ars": "https://ars.test.transltr.io/ars/api/"}[name])
    monkeypatch.setattr(
        ars.requests, "post",
        lambda url, json, timeout: posted.setdefault("url", url) and FakeResponse({"pk": PARENT}, 201),
    )

    ars.submit({"message": {"query_graph": {}}})

    assert posted["url"] == "https://ars.test.transltr.io/ars/api/submit"


def test_submit_rejects_unknown_shapes_and_http_failures(monkeypatch):
    with pytest.raises(ValueError, match="query must be"):
        ars.submit({"foo": 1}, base_url=BASE)

    monkeypatch.setattr(ars.requests, "post", lambda *a, **k: FakeResponse({"detail": "bad"}, 500))
    with pytest.raises(ars.ARSError, match="HTTP 500"):
        ars.submit({"message": {}}, base_url=BASE)

    monkeypatch.setattr(ars.requests, "post", lambda *a, **k: FakeResponse({"fields": {}}, 201))
    with pytest.raises(ars.ARSError, match="did not contain a pk"):
        ars.submit({"message": {}}, base_url=BASE)


def test_get_message_passes_trace_flag_and_maps_404(monkeypatch):
    seen = {}

    def fake_get(url, params, timeout):
        seen["url"] = url
        seen["params"] = params
        return FakeResponse({"status": "Running"}, 200)

    monkeypatch.setattr(ars.requests, "get", fake_get)
    ars.get_message(PARENT, trace=True, base_url=BASE)
    assert seen == {"url": BASE + f"messages/{PARENT}", "params": {"trace": "y"}}

    ars.get_message(PARENT, base_url=BASE)
    assert seen["params"] is None

    monkeypatch.setattr(ars.requests, "get", lambda *a, **k: FakeResponse({}, 404))
    with pytest.raises(LookupError):
        ars.get_message("missing", base_url=BASE)


def test_parse_trace_reads_children_and_merge_state():
    status = ars.parse_trace(PARENT, _done_trace())

    assert status.status == "Done"
    assert status.merged_version == MERGED
    assert [c.agent for c in status.children] == [ars.MERGE_AGENT, "ara-shepherd-arax"]
    assert status.merge_child.result_count == 3
    assert status.merged_ready
    assert status.is_terminal
    assert "ars-ars-agent=Done" in status.summary()

    # The ARS serialises merged_versions_list as a Python repr string.
    trace = _done_trace()
    trace["merged_versions_list"] = f"[['{MERGED}', 'ars'], ['child', 'ara-shepherd-arax']]"
    parsed = ars.parse_trace(PARENT, trace)
    assert parsed.merged_versions_list == [[MERGED, "ars"], ["child", "ara-shepherd-arax"]]
    assert ars.parse_trace(PARENT, {**trace, "merged_versions_list": [[MERGED, "ars"]]}).merged_versions_list == [[MERGED, "ars"]]
    assert ars.parse_trace(PARENT, {**trace, "merged_versions_list": "not a list"}).merged_versions_list == [["not a list"]]

    running = ars.parse_trace(PARENT, _trace("Running"))
    assert not running.is_terminal
    assert not running.merged_ready
    assert running.summary() == "no children yet"


# --------------------------------------------------------------------------- #
# wait_for_results
# --------------------------------------------------------------------------- #
def _poll_sequence(monkeypatch, traces):
    """Serve successive trace responses; the last one repeats."""
    calls = []

    def fake_get(url, params, timeout):
        index = min(len(calls), len(traces) - 1)
        calls.append(url)
        return FakeResponse(traces[index], 200)

    monkeypatch.setattr(ars.requests, "get", fake_get)
    return calls


def test_wait_returns_once_parent_and_merge_child_are_done(monkeypatch, no_sleep):
    calls = _poll_sequence(monkeypatch, [_trace("Running"), _trace("Running"), _done_trace()])

    status = ars.wait_for_results(PARENT, poll_interval=1, timeout=60, base_url=BASE)

    assert status.merged_version == MERGED
    assert len(calls) == 3
    assert no_sleep == [1, 1]


def test_wait_keeps_polling_when_parent_done_but_merge_child_still_running(monkeypatch, no_sleep):
    # NCATSTranslator/Relay#621: the parent flips to Done before the merged
    # message is saved. The merge child must also be Done before we return.
    calls = _poll_sequence(
        monkeypatch,
        [_done_trace(merge_status="Running"), _done_trace(merge_status="Running"), _done_trace()],
    )

    status = ars.wait_for_results(PARENT, poll_interval=1, timeout=60, base_url=BASE)

    assert status.merged_ready
    assert len(calls) == 3


def test_wait_returns_after_grace_when_no_merged_message_appears(monkeypatch, no_sleep):
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(ars.time, "monotonic", lambda: next(clock))
    calls = _poll_sequence(monkeypatch, [_trace("Done", None, [_child("ara-x", "Done")])])

    status = ars.wait_for_results(PARENT, poll_interval=1, timeout=600, merge_grace=25, base_url=BASE)

    assert status.status == "Done"
    assert status.merged_version is None
    assert len(calls) >= 2  # waited through the grace window, then returned


def test_wait_raises_on_error_status(monkeypatch, no_sleep):
    _poll_sequence(monkeypatch, [_trace("Error", None, [_child("ara-x", "Error", code=500)])])

    with pytest.raises(ars.ARSError, match="status Error"):
        ars.wait_for_results(PARENT, poll_interval=1, timeout=60, base_url=BASE)


def test_wait_times_out_instead_of_polling_forever(monkeypatch, no_sleep):
    clock = iter(range(0, 100000, 50))
    monkeypatch.setattr(ars.time, "monotonic", lambda: next(clock))
    calls = _poll_sequence(monkeypatch, [_trace("Running")])

    with pytest.raises(ars.ARSTimeoutError) as excinfo:
        ars.wait_for_results(PARENT, poll_interval=1, timeout=120, base_url=BASE)

    assert excinfo.value.status.status == "Running"
    assert 2 <= len(calls) <= 5


# --------------------------------------------------------------------------- #
# get_results / query / summarize
# --------------------------------------------------------------------------- #
def test_get_results_fetches_merged_message_or_falls_back_to_parent(monkeypatch):
    fetched = []

    def fake_get(url, params, timeout):
        fetched.append((url, params))
        if params:
            return FakeResponse(_done_trace(), 200)
        return FakeResponse(_envelope(_merged_message()), 200)

    monkeypatch.setattr(ars.requests, "get", fake_get)

    merged_pk, message = ars.get_results(PARENT, base_url=BASE)
    assert merged_pk == MERGED
    assert fetched[-1][0].endswith(f"messages/{MERGED}")
    assert len(message["results"]) == 2

    status = ars.parse_trace(PARENT, _trace("Done", None, []))
    merged_pk, _ = ars.get_results(status, base_url=BASE)
    assert merged_pk is None
    assert fetched[-1][0].endswith(f"messages/{PARENT}")


def test_query_runs_submit_wait_and_fetch(monkeypatch, no_sleep):
    monkeypatch.setattr(ars.requests, "post", lambda *a, **k: FakeResponse({"pk": PARENT}, 201))
    traces = [_trace("Running"), _done_trace()]
    polls = []

    def fake_get(url, params, timeout):
        if params:
            polls.append(url)
            return FakeResponse(traces[min(len(polls) - 1, len(traces) - 1)], 200)
        return FakeResponse(_envelope(_merged_message()), 200)

    monkeypatch.setattr(ars.requests, "get", fake_get)

    outcome = ars.query({"message": {"query_graph": {}}}, poll_interval=1, timeout=60, base_url=BASE)

    assert outcome.pk == PARENT
    assert outcome.merged_pk == MERGED
    assert len(outcome.results) == 2

    outcome = ars.query({"message": {}}, wait=False, base_url=BASE)
    assert outcome.message is None


def test_summarize_results_flattens_bindings_predicates_and_sources():
    rows = ars.summarize_results(_merged_message(), top_n=1)

    assert len(rows) == 1
    row = rows[0]
    assert row["rank"] == 1 and row["score"] == 0.9
    assert row["essence"] == "drug"
    assert row["nodes"]["n1"][0]["name"] == "drug"
    assert row["predicates"] == ["biolink:treats"]
    assert row["primary_sources"] == ["infores:a"]
    assert row["aras"] == ["infores:arax"]
    assert row["edge_count"] == 1

    assert len(ars.summarize_results(_merged_message(), top_n=None)) == 2
    assert ars.summarize_results(None) == []


# --------------------------------------------------------------------------- #
# ars_neighborhood_finder
# --------------------------------------------------------------------------- #
def test_ars_neighborhood_finder_resolves_to_curies_and_omits_empty_predicates(monkeypatch):
    submitted = {}

    monkeypatch.setattr(
        ars,
        "_resolve_nodes",
        lambda values, **kwargs: [
            ResolvedNode(input_value=v, curie=f"MONDO:{i}", label=v, categories=["biolink:Disease"])
            for i, v in enumerate([values] if isinstance(values, str) else values)
        ],
    )

    def fake_query(query_json, **kwargs):
        submitted.update(query_json)
        return ars.ARSResult(PARENT, ars.parse_trace(PARENT, _done_trace()), MERGED, _merged_message())

    monkeypatch.setattr(ars, "query", fake_query)

    result = ars.ars_neighborhood_finder("asthma", ["Drug"])

    graph = submitted["message"]["query_graph"]
    assert graph["nodes"]["n00"]["ids"] == ["MONDO:0"]
    assert graph["nodes"]["n01"]["categories"] == ["biolink:Drug"]
    assert "predicates" not in graph["edges"]["e00"] or graph["edges"]["e00"]["predicates"] is None
    assert isinstance(result, FinderResult)
    assert result.resolved_nodes["node"].curie == "MONDO:0"
    assert len(result.results) == 2


def test_ars_neighborhood_finder_returns_empty_finder_result_without_message(monkeypatch):
    monkeypatch.setattr(
        ars,
        "_resolve_nodes",
        lambda values, **kwargs: [
            ResolvedNode(input_value="MONDO:1", curie="MONDO:1", label="x", categories=[])
        ],
    )
    monkeypatch.setattr(
        ars,
        "query",
        lambda q, **k: ars.ARSResult(PARENT, ars.parse_trace(PARENT, _trace("Done")), None, None),
    )

    result = ars.ars_neighborhood_finder(["MONDO:1"], ["biolink:Gene"], predicates=["biolink:related_to"])

    assert result.results == []
    assert result.knowledge_graph == {"nodes": {}, "edges": {}}
    assert list(result.resolved_nodes) == ["node_0"]


# --------------------------------------------------------------------------- #
# agent-facing tools
# --------------------------------------------------------------------------- #
def test_query_ars_tool_returns_summary_or_full_message(monkeypatch):
    status = ars.parse_trace(PARENT, _done_trace())
    monkeypatch.setattr(
        tools, "ars_query",
        lambda q, **k: ars.ARSResult(PARENT, status, MERGED, _merged_message()),
    )

    summary = tools.query_ars({"message": {}}, top_n=1)
    assert summary["pk"] == PARENT
    assert summary["merged_pk"] == MERGED
    assert summary["result_count"] == 2
    assert len(summary["results"]) == 1
    assert "message" not in summary

    full = tools.query_ars({"message": {}}, top_n=0)
    assert full["message"]["results"][0]["essence"] == "drug"


def test_get_ars_results_tool_uses_status_then_fetches(monkeypatch):
    status = ars.parse_trace(PARENT, _done_trace())
    monkeypatch.setattr(tools, "ars_get_status", lambda pk: status)
    monkeypatch.setattr(tools, "ars_get_results", lambda s: (MERGED, _merged_message()))

    payload = tools.get_ars_results(PARENT, top_n=5)

    assert payload["merged_pk"] == MERGED
    assert payload["status"] is status
    assert payload["result_count"] == 2


def test_submit_ars_query_tool_returns_pk_and_status(monkeypatch):
    monkeypatch.setattr(tools, "ars_submit", lambda q: PARENT)
    monkeypatch.setattr(tools, "ars_get_status", lambda pk: ars.parse_trace(pk, _trace("Running")))

    payload = tools.submit_ars_query({"message": {}})

    assert payload["pk"] == PARENT
    assert payload["status"].status == "Running"


def test_ars_neighborhood_finder_tool_summarises_finder_result(monkeypatch):
    node = TranslatorNode(curie="MONDO:1", label="x", types=["biolink:Disease"])
    finder = FinderResult(
        query={}, knowledge_graph=_merged_message()["knowledge_graph"],
        results=_merged_message()["results"], auxiliary_graphs={},
        resolved_nodes={"node_0": node}, raw=_merged_message(),
    )
    monkeypatch.setattr(tools, "tct_ars_neighborhood_finder", lambda *a, **k: finder)

    summary = tools.ars_neighborhood_finder(["MONDO:1"], ["Drug"], top_n=1)
    assert summary["result_count"] == 2
    assert len(summary["results"]) == 1
    assert summary["resolved_nodes"]["node_0"] is node

    assert tools.ars_neighborhood_finder(["MONDO:1"], ["Drug"], top_n=0) is finder
