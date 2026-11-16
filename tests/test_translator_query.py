"""Offline tests for provider querying and merging."""

import time

from TCT import translator_query


def _message(edge_source):
    return {"knowledge_graph": {"edges": {"e1": {"source": edge_source}}}}


def test_merge_ignores_arrival_order_and_empty_answers(monkeypatch):
    delays = {}

    def fake_query_kp(name, query_json, api_names, api_predicates):
        time.sleep(delays[name])
        if name == "empty":
            return None
        if name == "broken":
            raise ConnectionError("refused")
        return _message(name)

    monkeypatch.setattr(translator_query, "query_KP", fake_query_kp)
    apis = ["zeta", "alpha", "empty", "broken"]
    merged = []
    for slow in ("alpha", "zeta"):
        delays.update({name: 0.0 for name in apis})
        delays[slow] = 0.2
        merged.append(
            translator_query.parallel_api_query({}, apis, {}, {}, max_workers=4)
        )

    assert merged[0] == merged[1] == {"e1": {"source": "zeta"}}


def test_provider_query_sets_a_timeout(monkeypatch):
    seen = {}

    class Response:
        status_code = 500

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return Response()

    monkeypatch.setattr(translator_query.requests, "post", fake_post)
    query = {
        "message": {
            "query_graph": {"edges": {"e00": {"predicates": ["biolink:treats"]}}}
        }
    }
    result = translator_query.query_KP(
        "kp", query, {"kp": "https://example.org/query"}, {"kp": []}
    )

    assert result is None
    assert seen["timeout"] == translator_query.PROVIDER_TIMEOUT
