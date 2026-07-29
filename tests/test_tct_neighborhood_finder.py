"""Tests for TCT.TCT_neighborhood_finder.

parse_results_for_neighborhood_finder is exercised directly (it is the key
compatibility point with the branch's KnowledgeGraph wrapper). The full
neighborhood_finder() pipeline is driven with mocked network calls.
"""

from unittest.mock import patch, MagicMock

import pytest

from TCT import TCT_neighborhood_finder as nf
from TCT.results import KnowledgeGraph
from TCT.translator_node import TranslatorNode


@pytest.fixture()
def neighborhood_edges():
    """Edges around start node MONDO:1, covering object-side, subject-side,
    a multi-edge intermediate, a missing-attributes edge, and an unrelated edge."""
    return {
        # start is subject -> intermediate is the object; carries category + name
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
        # second edge to the SAME intermediate (covers the append branch)
        "e1b": {
            "subject": "MONDO:1",
            "object": "CHEBI:1",
            "predicate": "biolink:affects",
            "sources": [{"resource_id": "infores:kp1b", "resource_role": "primary_knowledge_source"}],
            "attributes": [
                {"attribute_type_id": "object_category", "value": "biolink:Drug"},
            ],
        },
        # edge with NO attributes key (covers the `if 'attributes' not in v` guard)
        "e2": {
            "subject": "MONDO:1",
            "object": "CHEBI:2",
            "predicate": "biolink:affects",
            "sources": [{"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"}],
        },
        # start is object -> intermediate is the subject; subject-side attributes
        "e3": {
            "subject": "CHEBI:3",
            "object": "MONDO:1",
            "predicate": "biolink:treats",
            "sources": [{"resource_id": "infores:kp3", "resource_role": "primary_knowledge_source"}],
            "attributes": [
                {"attribute_type_id": "subject_category", "value": "biolink:Drug"},
                {"attribute_type_id": "subject_name", "value": "Drug Three"},
            ],
        },
        # unrelated edge (neither endpoint is the start node) -> skipped
        "e4": {
            "subject": "X:1",
            "object": "Y:1",
            "predicate": "biolink:related_to",
            "sources": [{"resource_id": "infores:kp4", "resource_role": "primary_knowledge_source"}],
            "attributes": [],
        },
    }


def test_parse_results_basic(neighborhood_edges):
    output = nf.parse_results_for_neighborhood_finder("MONDO:1", neighborhood_edges, get_node_info=False)
    assert set(output.keys()) == {"query_graph", "knowledge_graph", "results", "auxiliary_graphs"}
    nodes = output["knowledge_graph"]["nodes"]
    # three intermediates discovered, the unrelated edge's nodes excluded
    assert set(nodes.keys()) == {"CHEBI:1", "CHEBI:2", "CHEBI:3"}
    assert "X:1" not in nodes
    # CHEBI:1 accumulated two categories from its two edges
    assert set(nodes["CHEBI:1"]["categories"]) == {"biolink:SmallMolecule", "biolink:Drug"}
    # subject-side attributes captured
    assert nodes["CHEBI:3"]["name"] == "Drug Three"
    # CHEBI:1 (2 edges) should be the most-connected -> first auxiliary graph
    first_aux = next(iter(output["auxiliary_graphs"].values()))
    assert sorted(first_aux) == ["e1", "e1b"]


def test_parse_results_accepts_knowledge_graph(neighborhood_edges):
    """KnowledgeGraph wrapper (returned by parallel_api_query) is consumable here."""
    output = nf.parse_results_for_neighborhood_finder(
        "MONDO:1", KnowledgeGraph(edges=neighborhood_edges), get_node_info=False
    )
    assert set(output["knowledge_graph"]["nodes"].keys()) == {"CHEBI:1", "CHEBI:2", "CHEBI:3"}


def test_parse_results_get_node_info(neighborhood_edges):
    """get_node_info=True enriches name/categories via the (mocked) normalizer."""
    # CHEBI:2 has no name/category, so it needs enrichment
    fake = {"CHEBI:2": TranslatorNode(curie="CHEBI:2", label="Chem Two", types=["biolink:SmallMolecule"])}
    with patch("TCT.node_normalizer.get_normalized_nodes", return_value=fake) as mock_norm:
        output = nf.parse_results_for_neighborhood_finder("MONDO:1", neighborhood_edges, get_node_info=True)
    assert mock_norm.called
    assert output["knowledge_graph"]["nodes"]["CHEBI:2"]["name"] == "Chem Two"


def test_neighborhood_finder_pipeline(neighborhood_edges):
    """End-to-end with mocked network: input resolution, query, parse, rank."""

    def fake_norm(query, mode=None):
        if isinstance(query, str):
            return TranslatorNode(curie=query, label="Disease One", types=["biolink:Disease"])
        return {i: TranslatorNode(curie=i, label=f"n_{i}", types=["biolink:SmallMolecule"]) for i in query}

    with patch("TCT.node_normalizer.get_normalized_nodes", side_effect=fake_norm), \
         patch("TCT.TCT_neighborhood_finder.sele_predicates_API",
               return_value=(["biolink:related_to"], ["API_A"], ["http://api"])), \
         patch("TCT.translator_query.parallel_api_query",
               return_value=KnowledgeGraph(edges=neighborhood_edges)), \
         patch("TCT.TCT_neighborhood_finder.parse_KG", return_value=MagicMock()), \
         patch("TCT.TCT_neighborhood_finder.rank_by_primary_infores", return_value=MagicMock()):
        input_node_id, result, parsed_results, ranked = nf.neighborhood_finder(
            "MONDO:1", ["biolink:SmallMolecule"],
            APInames={"API_A": "http://api"}, metaKG=None, API_predicates={"API_A": []},
        )

    assert input_node_id == "MONDO:1"
    assert isinstance(result, KnowledgeGraph)
    assert set(parsed_results["knowledge_graph"]["nodes"].keys()) == {"CHEBI:1", "CHEBI:2", "CHEBI:3"}


def test_neighborhood_finder_input_category_intersection(neighborhood_edges):
    """When input_node_category is supplied, it intersects with resolved types."""

    def fake_norm(query, mode=None):
        if isinstance(query, str):
            return TranslatorNode(curie=query, label="Disease One", types=["biolink:Disease"])
        return {i: TranslatorNode(curie=i, label=f"n_{i}", types=["biolink:SmallMolecule"]) for i in query}

    with patch("TCT.node_normalizer.get_normalized_nodes", side_effect=fake_norm), \
         patch("TCT.TCT_neighborhood_finder.sele_predicates_API",
               return_value=(["biolink:related_to"], ["API_A"], ["http://api"])), \
         patch("TCT.translator_query.parallel_api_query",
               return_value=KnowledgeGraph(edges=neighborhood_edges)), \
         patch("TCT.TCT_neighborhood_finder.parse_KG", return_value=MagicMock()), \
         patch("TCT.TCT_neighborhood_finder.rank_by_primary_infores", return_value=MagicMock()):
        # supply a non-matching category -> falls back to resolved types
        input_node_id, *_ = nf.neighborhood_finder(
            "MONDO:1", ["biolink:SmallMolecule"],
            APInames={"API_A": "http://api"}, metaKG=None, API_predicates={"API_A": []},
            input_node_category=["biolink:Gene"],
        )
    assert input_node_id == "MONDO:1"
