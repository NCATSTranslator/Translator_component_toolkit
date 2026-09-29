"""ARS submission and result retrieval without live service calls."""

import pytest

from TCT import Query_ARS as ars
from TCT.interfaces import tools


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


def test_uploaded_json_is_submitted_unchanged_and_merged_result_returned(monkeypatch):
    query = {"message": {"query_graph": {"nodes": {"sn": {"ids": ["PUBCHEM.COMPOUND:132212657"]}, "on": {"ids": ["MONDO:0018874"]}}, "paths": {"p0": {"subject": "sn", "object": "on"}}}}, "submitter": "User"}
    calls = []

    def post(url, **kwargs):
        calls.append(("post", url, kwargs))
        return Response({"pk": "parent"})

    merged_result = {"fields": {"data": {"message": {"results": [1], "knowledge_graph": {}}}}}
    responses = iter([{"status": "Running"}, {"status": "Done", "merged_version": "merged"}, merged_result])

    def get(url, **kwargs):
        calls.append(("get", url, kwargs))
        return Response(next(responses))

    monkeypatch.setattr(ars.requests, "post", post)
    monkeypatch.setattr(ars.requests, "get", get)
    monkeypatch.setattr(ars.time, "sleep", lambda _: None)

    assert tools.ARS_neighborhood_finder(json_file=query) == merged_result
    assert calls[0] == ("post", f"{ars.BASE_URL}/submit", {"json": query, "timeout": 30})
    assert calls[-1][1] == f"{ars.BASE_URL}/messages/merged"
    assert calls[1][2]["params"] == {"trace": "y"}


def test_one_hop_input_matches_notebook_query(monkeypatch):
    captured = {}
    monkeypatch.setattr(ars, "Query_ARS", lambda url, query: captured.setdefault("query", query) and "pk")
    monkeypatch.setattr(ars, "check_ars_results", lambda pk, **kwargs: "merged")
    monkeypatch.setattr(ars, "fetch_ars_results", lambda pk, **kwargs: {"pk": pk})

    assert ars.ARS_neighborhood_finder("MONDO:0005148", ["biolink:Drug"]) == {"pk": "merged"}
    assert captured["query"] == {
        "message": {"query_graph": {
            "edges": {"e00": {"subject": "n00", "object": "n01", "predicates": ["biolink:related_to"]}},
            "nodes": {"n00": {"ids": ["MONDO:0005148"]}, "n01": {"categories": ["biolink:Drug"]}},
        }},
        "submitter": "TCT",
    }


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


def test_polling_stops_after_limit(monkeypatch):
    monkeypatch.setattr(ars.requests, "get", lambda *args, **kwargs: Response({"status": "Running"}))
    monkeypatch.setattr(ars.time, "sleep", lambda _: None)
    with pytest.raises(TimeoutError, match="after 2 checks"):
        ars.check_ars_results("pk", max_retries=2)


def test_done_without_merged_result_returns_none(monkeypatch):
    monkeypatch.setattr(ars, "Query_ARS", lambda url, query: "parent")
    monkeypatch.setattr(ars.requests, "get", lambda *args, **kwargs: Response({"status": "Done", "merged_version": None}))
    assert ars.ARS_neighborhood_finder(json_file={"message": {"query_graph": {}}}) is None


def test_invalid_uploaded_json_is_rejected_before_submission(monkeypatch):
    monkeypatch.setattr(ars.requests, "post", lambda *args, **kwargs: pytest.fail("unexpected POST"))
    with pytest.raises(ValueError, match="message.query_graph"):
        ars.ARS_neighborhood_finder(json_file={"message": None})
