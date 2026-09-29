"""Shared ARS fixtures: structural shapes of live ARS responses.

Adapted from the offline tests on ``feat/ars-client`` (Frankie Hodges). The
fixture-drift test in ``tests/test_ars_live.py`` asserts these structures stay
a subset of a real ARS trace and merged envelope when ``TCT_LIVE_ARS=1``.
"""

from __future__ import annotations

BASE = "https://ars.ci.transltr.io/ars/api/"
PARENT = "11111111-1111-1111-1111-111111111111"
MERGED = "22222222-2222-2222-2222-222222222222"


class FakeResponse:
    """Minimal ``requests.Response`` stand-in."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def child(agent, status, pk="child", result_count=None, code=200):
    """One ``children`` entry of a parent trace."""
    return {
        "actor": {"agent": agent, "inforesid": f"infores:{agent}"},
        "status": status,
        "code": code,
        "message": pk,
        "result_count": result_count,
    }


def trace(status, merged=None, children=()):
    """A ``?trace=y`` parent response."""
    return {
        "status": status,
        "code": 200 if status == "Done" else 202,
        "merged_version": merged,
        "merged_versions_list": [],
        "children": list(children),
    }


def done_trace(merged=MERGED, merge_status="Done"):
    """A parent trace whose merge agent has finished."""
    return trace(
        "Done",
        merged,
        [
            child("ars-ars-agent", merge_status, pk=merged, result_count="3"),
            child("ara-shepherd-arax", "Done", result_count=3),
        ],
    )


def merged_message():
    """A small but structurally complete merged TRAPI message."""
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
                        {
                            "resource_role": "primary_knowledge_source",
                            "resource_id": "infores:a",
                        },
                        {
                            "resource_role": "aggregator_knowledge_source",
                            "resource_id": "infores:agg",
                        },
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
                    {
                        "resource_id": "infores:arax",
                        "edge_bindings": {"e0": [{"id": "e1"}]},
                    }
                ],
            },
            {"rank": 2, "score": 0.1, "node_bindings": {}, "analyses": []},
        ],
        "auxiliary_graphs": {},
    }


def envelope(message, pk=MERGED):
    """A full ARS message envelope wrapping a merged TRAPI message."""
    return {
        "model": "tr_ars.message",
        "pk": pk,
        "fields": {"status": "Done", "data": {"message": message}},
    }
