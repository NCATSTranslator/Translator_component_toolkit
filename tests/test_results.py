"""Tests for TCT.results — SOLID result classes with built-in graph conversion."""

from unittest.mock import patch

import networkx as nx
import pandas as pd

from TCT.results import (
    GraphConvertible,
    KnowledgeGraph,
    NeighborhoodResult,
    ParsedKnowledgeGraph,
    PathResult,
    dataframe_to_graph,
)


# ---------------------------------------------------------------------------
# KnowledgeGraph tests
# ---------------------------------------------------------------------------


class TestKnowledgeGraph:
    def test_to_networkx_basic(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        G = kg.to_networkx()

        assert isinstance(G, nx.MultiDiGraph)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 4

    def test_to_networkx_sources(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        G = kg.to_networkx()

        # edge1 has primary_knowledge_source=kp1, aggregator_knowledge_source=agg1
        edge1_data = G.edges["NCBIGene:3845", "CHEBI:15377", "edge1"]
        assert edge1_data["primary_sources"] == ["infores:kp1"]
        assert edge1_data["aggregator_sources"] == ["infores:agg1"]

        # edge4 has only primary_knowledge_source=kp4
        edge4_data = G.edges["NCBIGene:3845", "MONDO:0005148", "edge4"]
        assert edge4_data["primary_sources"] == ["infores:kp4"]
        assert edge4_data["aggregator_sources"] == []

    @patch("TCT.node_normalizer.get_preferred_names")
    def test_to_networkx_resolve_names(self, mock_names, sample_kg_result):
        mock_names.return_value = {
            "NCBIGene:3845": "KRAS",
            "CHEBI:15377": "Water",
            "MONDO:0005148": "type 2 diabetes mellitus",
        }
        kg = KnowledgeGraph(edges=sample_kg_result)
        G = kg.to_networkx(resolve_names=True)

        assert G.nodes["NCBIGene:3845"]["label"] == "KRAS"
        assert G.nodes["CHEBI:15377"]["label"] == "Water"
        mock_names.assert_called_once()

    def test_to_networkx_empty(self):
        kg = KnowledgeGraph(edges={})
        G = kg.to_networkx()

        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_parse(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()

        assert isinstance(parsed, ParsedKnowledgeGraph)
        # edge1 and edge2 share subject-object pair NCBIGene:3845_CHEBI:15377
        key = "NCBIGene:3845_CHEBI:15377"
        assert key in parsed
        assert parsed[key]["subject"] == "NCBIGene:3845"
        assert parsed[key]["object"] == "CHEBI:15377"
        assert len(parsed[key]["predicate"]) == 2
        assert "biolink:interacts_with" in parsed[key]["predicate"]
        assert "biolink:related_to" in parsed[key]["predicate"]

    def test_to_dataframe(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        df = kg.to_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert set(df.columns) == {"Subject", "Object", "Predicate"}
        assert len(df) == 4

    def test_dict_like_access(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)

        assert len(kg) == 4
        assert "edge1" in kg
        assert "nonexistent" not in kg
        assert kg["edge1"]["subject"] == "NCBIGene:3845"
        assert set(kg.keys()) == {"edge1", "edge2", "edge3", "edge4"}
        assert len(list(kg.items())) == 4
        assert len(list(kg.values())) == 4
        assert kg.get("edge1") is not None
        assert kg.get("missing", "default") == "default"

        # Iteration
        keys = [k for k in kg]
        assert len(keys) == 4

    def test_implements_graph_convertible(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        assert isinstance(kg, GraphConvertible)

    def test_to_networkx_default_excludes_rich_attributes(self, sample_kg_result_with_attributes):
        kg = KnowledgeGraph(edges=sample_kg_result_with_attributes)
        G = kg.to_networkx()
        for _u, _v, data in G.edges(data=True):
            assert "publications" not in data
            assert "supporting_text" not in data
            assert "confidence_scores" not in data

    def test_to_networkx_include_attributes_adds_publications(self, sample_kg_result_with_attributes):
        kg = KnowledgeGraph(edges=sample_kg_result_with_attributes)
        G = kg.to_networkx(include_attributes=True)
        edge_data = G.edges["NCBIGene:3845", "CHEBI:15377", "edge_top_level_pubs"]
        assert edge_data["publications"] == ["PMID:123", "PMID:456"]

    def test_to_networkx_include_attributes_adds_supporting_text(self, sample_kg_result_with_attributes):
        kg = KnowledgeGraph(edges=sample_kg_result_with_attributes)
        G = kg.to_networkx(include_attributes=True)
        edge_data = G.edges["NCBIGene:3845", "MONDO:0005148", "edge_nested_study_result"]
        assert "Gene X is associated with disease Y." in edge_data["supporting_text"]

    def test_to_networkx_include_attributes_adds_confidence_scores(self, sample_kg_result_with_attributes):
        kg = KnowledgeGraph(edges=sample_kg_result_with_attributes)
        G = kg.to_networkx(include_attributes=True)
        edge_data = G.edges["CHEBI:15377", "NCBIGene:3845", "edge_legacy_sentences_tmkp"]
        assert edge_data["confidence_scores"]["tmkp_confidence_score"] == 0.87

    def test_to_networkx_include_attributes_empty_edge(self, sample_kg_result_with_attributes):
        kg = KnowledgeGraph(edges=sample_kg_result_with_attributes)
        G = kg.to_networkx(include_attributes=True)
        edge_data = G.edges["NCBIGene:7157", "MONDO:0005148", "edge_empty_attributes"]
        assert edge_data["publications"] == []
        assert edge_data["supporting_text"] == []
        assert edge_data["confidence_scores"] == {}


# ---------------------------------------------------------------------------
# ParsedKnowledgeGraph tests
# ---------------------------------------------------------------------------


class TestParsedKnowledgeGraph:
    @patch("TCT.node_normalizer.convert_ids_to_preferred_names")
    def test_to_networkx(self, mock_names, sample_kg_result):
        mock_names.return_value = []
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        G = parsed.to_networkx()

        assert isinstance(G, nx.MultiDiGraph)
        assert G.number_of_nodes() == 3
        # Each unique (subject, object, predicate) becomes an edge
        assert G.number_of_edges() > 0

    @patch("TCT.node_normalizer.convert_ids_to_preferred_names")
    def test_rank(self, mock_names, sample_kg_result):
        # 3 output nodes: CHEBI:15377 (from NCBIGene:3845_CHEBI:15377),
        # CHEBI:15377 (from CHEBI:15377_NCBIGene:3845), MONDO:0005148
        mock_names.return_value = ["Water", "Water", "type 2 diabetes mellitus"]
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        ranked = parsed.rank("NCBIGene:3845")

        assert isinstance(ranked, pd.DataFrame)
        assert "output_node" in ranked.columns
        assert "Name" in ranked.columns
        assert "Num_of_primary_infores" in ranked.columns
        assert "type_of_nodes" in ranked.columns
        assert "unique_predicates" in ranked.columns
        # Should be sorted descending by Num_of_primary_infores
        infores_vals = ranked["Num_of_primary_infores"].tolist()
        assert infores_vals == sorted(infores_vals, reverse=True)

    def test_dict_like_access(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()

        assert len(parsed) > 0
        first_key = next(iter(parsed))
        assert first_key in parsed
        entry = parsed[first_key]
        assert "subject" in entry
        assert "object" in entry
        assert "predicate" in entry
        assert len(list(parsed.items())) == len(parsed)
        assert len(list(parsed.values())) == len(parsed)
        assert len(list(parsed.keys())) == len(parsed)
        assert parsed.get(first_key) is not None
        assert parsed.get("nonexistent", "fallback") == "fallback"

    def test_implements_graph_convertible(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        assert isinstance(parsed, GraphConvertible)


# ---------------------------------------------------------------------------
# NeighborhoodResult tests
# ---------------------------------------------------------------------------


class TestNeighborhoodResult:
    def test_to_networkx(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = NeighborhoodResult(
            input_node_id="NCBIGene:3845",
            knowledge_graph=kg,
            parsed=parsed,
            ranked=pd.DataFrame(),
        )
        G = result.to_networkx()

        assert isinstance(G, nx.MultiDiGraph)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 4

    def test_fields(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        ranked_df = pd.DataFrame({"col": [1, 2]})
        result = NeighborhoodResult(
            input_node_id="NCBIGene:3845",
            knowledge_graph=kg,
            parsed=parsed,
            ranked=ranked_df,
        )

        assert result.input_node_id == "NCBIGene:3845"
        assert isinstance(result.knowledge_graph, KnowledgeGraph)
        assert isinstance(result.parsed, ParsedKnowledgeGraph)
        assert isinstance(result.ranked, pd.DataFrame)

    def test_implements_graph_convertible(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = NeighborhoodResult(
            input_node_id="NCBIGene:3845",
            knowledge_graph=kg,
            parsed=parsed,
            ranked=pd.DataFrame(),
        )
        assert isinstance(result, GraphConvertible)


# ---------------------------------------------------------------------------
# PathResult tests
# ---------------------------------------------------------------------------


class TestPathResult:
    def test_to_networkx(self, sample_kg_result):
        kg1 = KnowledgeGraph(edges=sample_kg_result)
        # Create a second KG with different edges
        kg2_edges = {
            "edge5": {
                "subject": "MONDO:0005148",
                "object": "CHEBI:99999",
                "predicate": "biolink:treats",
                "sources": [
                    {
                        "resource_id": "infores:kp5",
                        "resource_role": "primary_knowledge_source",
                    },
                ],
                "attributes": [],
            }
        }
        kg2 = KnowledgeGraph(edges=kg2_edges)
        parsed1 = kg1.parse()
        parsed2 = kg2.parse()
        result = PathResult(
            paths=pd.DataFrame(),
            node1_id="NCBIGene:3845",
            node2_id="CHEBI:99999",
            knowledge_graph1=kg1,
            knowledge_graph2=kg2,
            parsed1=parsed1,
            parsed2=parsed2,
            ranked1=pd.DataFrame(),
            ranked2=pd.DataFrame(),
        )
        G = result.to_networkx()

        assert isinstance(G, nx.MultiDiGraph)
        # Merged graph should have nodes from both KGs
        assert "NCBIGene:3845" in G.nodes()
        assert "CHEBI:99999" in G.nodes()
        assert G.number_of_edges() == 5  # 4 from kg1 + 1 from kg2

    def test_fields(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = PathResult(
            paths=pd.DataFrame({"path": [1]}),
            node1_id="node1",
            node2_id="node2",
            knowledge_graph1=kg,
            knowledge_graph2=kg,
            parsed1=parsed,
            parsed2=parsed,
            ranked1=pd.DataFrame(),
            ranked2=pd.DataFrame(),
        )

        assert result.node1_id == "node1"
        assert result.node2_id == "node2"
        assert isinstance(result.paths, pd.DataFrame)
        assert isinstance(result.knowledge_graph1, KnowledgeGraph)
        assert isinstance(result.knowledge_graph2, KnowledgeGraph)

    def test_implements_graph_convertible(self, sample_kg_result):
        kg = KnowledgeGraph(edges=sample_kg_result)
        parsed = kg.parse()
        result = PathResult(
            paths=pd.DataFrame(),
            node1_id="n1",
            node2_id="n2",
            knowledge_graph1=kg,
            knowledge_graph2=kg,
            parsed1=parsed,
            parsed2=parsed,
            ranked1=pd.DataFrame(),
            ranked2=pd.DataFrame(),
        )
        assert isinstance(result, GraphConvertible)


# ---------------------------------------------------------------------------
# dataframe_to_graph tests
# ---------------------------------------------------------------------------


class TestDataframeToGraph:
    def test_default_cols(self):
        df = pd.DataFrame(
            {
                "Subject": ["A", "B"],
                "Object": ["B", "C"],
                "Predicate": ["biolink:related_to", "biolink:treats"],
            }
        )
        G = dataframe_to_graph(df, edge_attrs=["Predicate"])

        assert isinstance(G, nx.MultiDiGraph)
        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 2

    def test_custom_cols(self):
        df = pd.DataFrame(
            {
                "src": ["X", "Y"],
                "dst": ["Y", "Z"],
                "weight": [1.0, 2.0],
            }
        )
        G = dataframe_to_graph(
            df, source_col="src", target_col="dst", edge_attrs=["weight"]
        )

        assert G.number_of_nodes() == 3
        assert G.number_of_edges() == 2

    def test_metakg_dataframe(self, sample_metakg):
        G = dataframe_to_graph(
            sample_metakg,
            source_col="Subject",
            target_col="Object",
            edge_attrs=["Predicate", "API"],
        )

        assert isinstance(G, nx.MultiDiGraph)
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() == len(sample_metakg)
