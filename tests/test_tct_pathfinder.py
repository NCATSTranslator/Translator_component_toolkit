"""Tests for TCT.TCT_pathfinder.

Pure query-building / parsing / scoring helpers are tested directly. The
network-bound endpoint wrappers and the full pathfinder() pipeline are tested
with mocks (no live HTTP).
"""

from unittest.mock import patch, MagicMock

import pytest

from TCT import TCT_pathfinder
from TCT.results import KnowledgeGraph
from TCT.translator_node import TranslatorNode


# ---------------------------------------------------------------------------
# Fixtures: two TRAPI-edge result sets sharing an intermediate node
# ---------------------------------------------------------------------------

@pytest.fixture()
def result1():
    """Edges from the start node (MONDO:1) to intermediate CHEBI:1."""
    return {
        "e1": {
            "subject": "MONDO:1",
            "object": "CHEBI:1",
            "predicate": "biolink:related_to",
            "sources": [{"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"}],
            "attributes": [
                {"attribute_type_id": "object_category", "value": "biolink:SmallMolecule"},
                {"attribute_type_id": "object_name", "value": "Chem One"},
            ],
        },
    }


@pytest.fixture()
def result2():
    """Edges from the end node (MONDO:2) to the same intermediate CHEBI:1."""
    return {
        "e2": {
            "subject": "MONDO:2",
            "object": "CHEBI:1",
            "predicate": "biolink:affects",
            "sources": [{"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"}],
            "attributes": [
                {"attribute_type_id": "object_category", "value": "biolink:SmallMolecule"},
            ],
        },
    }


# ---------------------------------------------------------------------------
# format_query_json_for_pathfinder_with_constraints
# ---------------------------------------------------------------------------

def test_format_query_json_with_constraints():
    q = TCT_pathfinder.format_query_json_for_pathfinder_with_constraints(
        "MONDO:1", "MONDO:2", constraints=["biolink:Gene"]
    )
    path = q["message"]["query_graph"]["paths"]["p0"]
    assert path["constraints"][0]["intermediate_categories"] == ["biolink:Gene"]
    assert q["submitter"] == "TCT"


def test_format_query_json_without_constraints():
    q = TCT_pathfinder.format_query_json_for_pathfinder_with_constraints("MONDO:1", "MONDO:2")
    path = q["message"]["query_graph"]["paths"]["p0"]
    assert path["constraints"][0]["intermediate_categories"] is None


# ---------------------------------------------------------------------------
# build_query_graph
# ---------------------------------------------------------------------------

def test_build_query_graph():
    q = TCT_pathfinder.build_query_graph("MONDO:1", "MONDO:2", ["biolink:Disease"], ["biolink:Drug"])
    assert q["nodes"]["sn"]["ids"] == ["MONDO:1"]
    assert q["nodes"]["on"]["ids"] == ["MONDO:2"]
    assert q["nodes"]["sn"]["categories"] == ["biolink:Disease"]
    assert q["paths"]["p0"]["subject"] == "sn"
    assert q["paths"]["p0"]["object"] == "on"


# ---------------------------------------------------------------------------
# generate_score_results
# ---------------------------------------------------------------------------

def _scoring_input():
    return {
        "knowledge_graph": {
            "edges": {
                "e1": {"sources": [{"resource_id": "infores:a"}, {"resource_id": "infores:b"}]},
                "e2": {"sources": [{"resource_id": "infores:a"}]},
            }
        },
        "auxiliary_graphs": {
            "aux_1": ["e1", "e2"],
            "aux_2": ["e2"],
        },
    }


def test_generate_score_results_infores():
    scores, formatted = TCT_pathfinder.generate_score_results(_scoring_input(), method="infores")
    # aux_1 has sources {a, b} -> 2; aux_2 has {a} -> 1; normalized by max (2)
    assert scores["aux_1"] == 1.0
    assert scores["aux_2"] == 0.5
    assert all("path_bindings" in entry for entry in formatted)
    assert formatted[0]["resource_id"] == "infores:tct"


def test_generate_score_results_edges():
    scores, _ = TCT_pathfinder.generate_score_results(_scoring_input(), method="edges")
    # aux_1 has 2 edges, aux_2 has 1; normalized by max (2)
    assert scores["aux_1"] == 1.0
    assert scores["aux_2"] == 0.5


# ---------------------------------------------------------------------------
# parse_results_for_pathfinder
# ---------------------------------------------------------------------------

def test_parse_results_for_pathfinder(result1, result2):
    output = TCT_pathfinder.parse_results_for_pathfinder(
        "MONDO:1", "MONDO:2", result1, result2, get_node_info=False
    )
    assert set(output.keys()) == {"query_graph", "knowledge_graph", "results", "auxiliary_graphs"}
    # both edges land in the merged knowledge graph
    assert set(output["knowledge_graph"]["edges"].keys()) == {"e1", "e2"}
    # one auxiliary graph for the single connecting node, containing both edges
    aux = list(output["auxiliary_graphs"].values())
    assert aux and sorted(aux[0]) == ["e1", "e2"]
    # node categories were collected and converted from set to list
    chem = output["knowledge_graph"]["nodes"]["CHEBI:1"]
    assert chem["categories"] == ["biolink:SmallMolecule"]
    assert chem["name"] == "Chem One"


def test_parse_results_for_pathfinder_all_branches():
    """Exercise object-side, subject-side, multi-edge, unrelated, and new-node branches."""
    def src(rid):
        return [{"resource_id": rid, "resource_role": "primary_knowledge_source"}]
    result1 = {
        # start -> M1 (object side), with category + name
        "r1a": {"subject": "S", "object": "M1", "predicate": "biolink:related_to", "sources": src("i:1"),
                "attributes": [{"attribute_type_id": "object_category", "value": "CatA"},
                               {"attribute_type_id": "object_name", "value": "NameM1"}]},
        # second edge to M1 (append + existing node_dict + categories.add)
        "r1b": {"subject": "S", "object": "M1", "predicate": "biolink:affects", "sources": src("i:2"),
                "attributes": [{"attribute_type_id": "object_category", "value": "CatB"}]},
        # M2 -> start (subject side)
        "r1c": {"subject": "M2", "object": "S", "predicate": "biolink:treats", "sources": src("i:3"),
                "attributes": [{"attribute_type_id": "subject_category", "value": "CatC"},
                               {"attribute_type_id": "subject_name", "value": "NameM2"}]},
        # unrelated edge -> continue
        "r1d": {"subject": "P", "object": "Q", "predicate": "biolink:related_to", "sources": src("i:4"),
                "attributes": []},
    }
    result2 = {
        # end -> M1 (object side) -> connecting
        "r2a": {"subject": "E", "object": "M1", "predicate": "biolink:related_to", "sources": src("i:5"),
                "attributes": [{"attribute_type_id": "object_category", "value": "CatA"}]},
        # second end edge to M1 -> connecting append
        "r2b": {"subject": "E", "object": "M1", "predicate": "biolink:affects", "sources": src("i:6"),
                "attributes": []},
        # M2 -> end (subject side) -> connecting, with subject_name
        "r2c": {"subject": "M2", "object": "E", "predicate": "biolink:treats", "sources": src("i:7"),
                "attributes": [{"attribute_type_id": "subject_category", "value": "CatC"},
                               {"attribute_type_id": "subject_name", "value": "NameM2b"}]},
        # M3 -> end, M3 not in result1 -> new node_info, not connecting
        "r2d": {"subject": "M3", "object": "E", "predicate": "biolink:treats", "sources": src("i:8"),
                "attributes": [{"attribute_type_id": "subject_name", "value": "NameM3"}]},
        # unrelated edge -> continue
        "r2e": {"subject": "P2", "object": "Q2", "predicate": "biolink:related_to", "sources": src("i:9"),
                "attributes": []},
    }
    output = TCT_pathfinder.parse_results_for_pathfinder("S", "E", result1, result2, get_node_info=False)
    # M1 and M2 are the connecting intermediates
    assert set(output["knowledge_graph"]["nodes"].keys()) == {"M1", "M2"}
    # M1 accumulated both categories
    assert set(output["knowledge_graph"]["nodes"]["M1"]["categories"]) == {"CatA", "CatB"}


def test_parse_results_for_pathfinder_accepts_knowledge_graph(result1, result2):
    """The branch's KnowledgeGraph wrapper is consumable by upstream's parser."""
    output = TCT_pathfinder.parse_results_for_pathfinder(
        "MONDO:1", "MONDO:2", KnowledgeGraph(edges=result1), KnowledgeGraph(edges=result2),
        get_node_info=False,
    )
    assert set(output["knowledge_graph"]["edges"].keys()) == {"e1", "e2"}


def test_parse_results_for_pathfinder_get_node_info(result1, result2):
    """get_node_info=True path uses the node normalizer (mocked)."""
    fake = {"CHEBI:1": TranslatorNode(curie="CHEBI:1", label="Chem One", types=["biolink:SmallMolecule"])}
    with patch("TCT.node_normalizer.get_normalized_nodes", return_value=fake) as mock_norm:
        # strip name/categories so the node needs enrichment
        result1["e1"]["attributes"] = []
        output = TCT_pathfinder.parse_results_for_pathfinder(
            "MONDO:1", "MONDO:2", result1, result2, get_node_info=True
        )
    assert mock_norm.called
    assert "CHEBI:1" in output["knowledge_graph"]["nodes"]


# ---------------------------------------------------------------------------
# format_pathfinder_query + endpoint wrappers (mocked HTTP)
# ---------------------------------------------------------------------------

def test_format_pathfinder_query():
    q = TCT_pathfinder.format_pathfinder_query("MONDO:1", "biolink:Disease", "MONDO:2", "biolink:Drug")
    nodes = q["message"]["query_graph"]["nodes"]
    assert nodes["SN"]["ids"] == ["MONDO:1"]
    assert nodes["ON"]["categories"] == ["biolink:Drug"]


@pytest.mark.parametrize("fn,expected_host", [
    ("query_aragorn_pathfinder", "shepherd.renci.org"),
    ("query_arax_pathfinder", "arax.ci.transltr.io"),
])
def test_endpoint_wrappers(fn, expected_host):
    with patch("TCT.TCT_pathfinder.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        resp = getattr(TCT_pathfinder, fn)("MONDO:1", "biolink:Disease", "MONDO:2", "biolink:Drug")
    assert resp.status_code == 200
    called_url = mock_post.call_args[0][0]
    assert expected_host in called_url


@pytest.mark.parametrize("fn,expected_host", [
    ("query_aragorn_pathfinder_with_constraints", "shepherd.renci.org"),
    ("query_arax_pathfinder_with_constraints", "arax.ci.transltr.io"),
])
def test_endpoint_wrappers_with_constraints(fn, expected_host):
    with patch("TCT.TCT_pathfinder.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        resp = getattr(TCT_pathfinder, fn)(
            "MONDO:1", "biolink:Disease", "MONDO:2", "biolink:Drug", ["biolink:Gene"]
        )
    assert resp.status_code == 200
    assert expected_host in mock_post.call_args[0][0]


# ---------------------------------------------------------------------------
# pathfinder() full pipeline (mocked network)
# ---------------------------------------------------------------------------

def test_pathfinder_pipeline(result1, result2):
    nodes = {
        "MONDO:1": TranslatorNode(curie="MONDO:1", label="D1", types=["biolink:Disease"]),
        "MONDO:2": TranslatorNode(curie="MONDO:2", label="D2", types=["biolink:Disease"]),
        "CHEBI:1": TranslatorNode(curie="CHEBI:1", label="Chem One", types=["biolink:SmallMolecule"]),
    }

    def fake_norm(ids, mode=None):
        return {i: nodes[i] for i in ids if i in nodes}

    with patch("TCT.node_normalizer.get_normalized_nodes", side_effect=fake_norm), \
         patch("TCT.TCT_pathfinder.sele_predicates_API",
               return_value=(["biolink:related_to"], ["API_A"], ["http://api"])), \
         patch("TCT.translator_query.parallel_api_query",
               side_effect=[KnowledgeGraph(edges=result1), KnowledgeGraph(edges=result2)]):
        r1, r2, output = TCT_pathfinder.pathfinder(
            "MONDO:1", "MONDO:2", ["biolink:SmallMolecule"],
            APInames={"API_A": "http://api"}, metaKG=None, API_predicates={"API_A": []},
        )

    assert isinstance(r1, KnowledgeGraph)
    assert set(output["knowledge_graph"]["edges"].keys()) == {"e1", "e2"}
