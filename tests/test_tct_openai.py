"""Tests for OpenAI/chatGPT functions, Neighborhood/Path finders, and connecting_two_dots_two_hops."""

import sys
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock

import TCT.TCT as tct


# ---------------------------------------------------------------------------
# Helper: Build a mock openai module so that patching openai.chat.completions.create
# works without requiring a real API key.
# ---------------------------------------------------------------------------

def _make_openai_mock(content="test response"):
    """Return a MagicMock that mimics the openai module, pre-configured
    so that ``openai.chat.completions.create(...)`` returns *content*."""
    mock_openai = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    mock_openai.chat.completions.create.return_value = mock_response
    return mock_openai


# ---------------------------------------------------------------------------
# 1. query_chatGPT
# ---------------------------------------------------------------------------

class TestQueryChatGPT:
    """Tests for query_chatGPT(customized_input, model)."""

    def test_returns_response_content(self):
        mock_openai = _make_openai_mock("test response")
        with patch.object(tct, "openai", mock_openai):
            result = tct.query_chatGPT("Hello")
        assert result == "test response"

    def test_default_model_is_gpt35_turbo(self):
        mock_openai = _make_openai_mock("ok")
        with patch.object(tct, "openai", mock_openai):
            tct.query_chatGPT("Hello")
        call_kwargs = mock_openai.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-3.5-turbo"

    def test_custom_model(self):
        mock_openai = _make_openai_mock("custom")
        with patch.object(tct, "openai", mock_openai):
            result = tct.query_chatGPT("Hello", model="gpt-4o")
        assert result == "custom"
        assert mock_openai.chat.completions.create.call_args.kwargs["model"] == "gpt-4o"


# ---------------------------------------------------------------------------
# 2. query_chatGPT4
# ---------------------------------------------------------------------------

class TestQueryChatGPT4:
    """Tests for query_chatGPT4(customized_input)."""

    def test_calls_with_gpt4_model(self):
        mock_openai = _make_openai_mock("gpt4 response")
        with patch.object(tct, "openai", mock_openai):
            result = tct.query_chatGPT4("Hello")
        assert result == "gpt4 response"
        assert mock_openai.chat.completions.create.call_args.kwargs["model"] == "gpt-4"


# ---------------------------------------------------------------------------
# 3. ask_chatGPT
# ---------------------------------------------------------------------------

class TestAskChatGPT:
    """Tests for ask_chatGPT(prompt_text)."""

    @patch("TCT.TCT.query_chatGPT")
    def test_delegates_to_query_chatGPT(self, mock_query):
        mock_query.return_value = "delegated response"

        result = tct.ask_chatGPT("test prompt")
        mock_query.assert_called_once_with("test prompt")
        assert result == "delegated response"


# ---------------------------------------------------------------------------
# 4. ask_chatGPT4
# ---------------------------------------------------------------------------

class TestAskChatGPT4:
    """Tests for ask_chatGPT4(prompt_text)."""

    @patch("TCT.TCT.query_chatGPT4")
    def test_delegates_to_query_chatGPT4(self, mock_query4):
        mock_query4.return_value = "gpt4 delegated"

        result = tct.ask_chatGPT4("test prompt")
        mock_query4.assert_called_once_with("test prompt")
        assert result == "gpt4 delegated"


# ---------------------------------------------------------------------------
# 5. find_similar_predicates
# ---------------------------------------------------------------------------

class TestFindSimilarPredicates:
    """Tests for find_similar_predicates(query_json, ALL_predicates)."""

    @patch("TCT.TCT.ask_chatGPT4")
    def test_prompt_includes_predicates(self, mock_ask):
        mock_ask.return_value = "biolink:interacts_with is similar"

        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e1": {
                            "predicates": ["biolink:treats", "biolink:affects"]
                        }
                    }
                }
            }
        }
        all_predicates = ["biolink:interacts_with", "biolink:related_to", "biolink:treats"]

        result = tct.find_similar_predicates(query_json, all_predicates)

        assert result == "biolink:interacts_with is similar"
        prompt_arg = mock_ask.call_args[0][0]
        # The prompt should contain the ALL_predicates
        for pred in all_predicates:
            assert pred in prompt_arg
        # The prompt should contain the query predicates
        assert "biolink:treats" in prompt_arg
        assert "biolink:affects" in prompt_arg


# ---------------------------------------------------------------------------
# 6. find_similar_category
# ---------------------------------------------------------------------------

class TestFindSimilarCategory:
    """Tests for find_similar_category(query_json, ALL_categories)."""

    @patch("TCT.TCT.ask_chatGPT4")
    def test_prompt_includes_categories(self, mock_ask):
        mock_ask.return_value = "biolink:Gene is similar"

        query_json = {
            "message": {
                "query_graph": {
                    "nodes": {
                        "n0": {"categories": ["biolink:Gene"]},
                        "n1": {"categories": ["biolink:Disease"]},
                    }
                }
            }
        }
        all_categories = ["biolink:Gene", "biolink:Disease", "biolink:SmallMolecule"]

        result = tct.find_similar_category(query_json, all_categories)

        assert result == "biolink:Gene is similar"
        prompt_arg = mock_ask.call_args[0][0]
        for cat in all_categories:
            assert cat in prompt_arg
        assert "biolink:Gene" in prompt_arg
        assert "biolink:Disease" in prompt_arg


# ---------------------------------------------------------------------------
# 7. get_similar_category
# ---------------------------------------------------------------------------

class TestGetSimilarCategory:
    """Tests for get_similar_category(query_json, KG_category)."""

    @patch("TCT.TCT.find_similar_category")
    def test_returns_list_with_matched_categories(self, mock_find):
        mock_find.return_value = "biolink:SmallMolecule is similar to biolink:Gene"

        query_json = {
            "message": {
                "query_graph": {
                    "nodes": {
                        "n0": {"categories": ["biolink:Gene"]},
                        "n1": {"categories": ["biolink:Disease"]},
                    }
                }
            }
        }
        kg_categories = ["biolink:Gene", "biolink:Disease", "biolink:SmallMolecule"]

        result = tct.get_similar_category(query_json, kg_categories)

        # The function extracts biolink: words from the GPT response,
        # adds categories from n0 and n1 if they are in KG_category,
        # then appends all of KG_category.
        assert isinstance(result, list)
        # "biolink:SmallMolecule" should be found in the response text and be in KG_category
        assert "biolink:SmallMolecule" in result
        # n0 category "biolink:Gene" is in KG_category, so it should appear
        assert "biolink:Gene" in result
        # n1 category "biolink:Disease" is in KG_category, so it should appear
        assert "biolink:Disease" in result
        # All KG_category items are appended at the end
        for cat in kg_categories:
            assert cat in result


# ---------------------------------------------------------------------------
# 8. get_similar_predicate
# ---------------------------------------------------------------------------

class TestGetSimilarPredicate:
    """Tests for get_similar_predicate(query_json, All_predicates)."""

    @patch("TCT.TCT.find_similar_predicates")
    def test_returns_list_with_matched_predicates(self, mock_find):
        mock_find.return_value = "biolink:interacts_with\nbiolink:related_to are similar"

        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e1": {
                            "predicates": ["biolink:treats"]
                        }
                    }
                }
            }
        }
        all_predicates = ["biolink:interacts_with", "biolink:related_to", "biolink:treats"]

        result = tct.get_similar_predicate(query_json, all_predicates)

        assert isinstance(result, list)
        # "biolink:interacts_with" and "biolink:related_to" found in GPT response
        assert "biolink:interacts_with" in result
        assert "biolink:related_to" in result
        # "biolink:treats" is from the query predicates, also added
        assert "biolink:treats" in result


# ---------------------------------------------------------------------------
# 9. Neighborhood_finder_mcp -- known NameError bug
# ---------------------------------------------------------------------------

class TestNeighborhoodFinderMcp:
    """Tests for Neighborhood_finder_mcp(input_node, node2_categories).

    This function has a known bug: it references ``input_node_category`` which
    is not defined as a local variable or parameter before its first use.
    """

    def test_raises_name_error_due_to_bug(self):
        # The function does lazy imports:
        #   from . import translator_metakg
        #   from . import translator_kpinfo
        # Then calls translator_metakg.load_translator_resources() and
        # name_resolver.lookup() before hitting the bug.
        # We mock at the actual submodule level and also patch the
        # top-level name_resolver import.

        sample_apinames = {"API_A": "https://api-a.example.com/query"}
        sample_metakg = pd.DataFrame({
            "API": ["API_A"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:SmallMolecule"],
            "URL": ["https://api-a.example.com/query"],
        })
        sample_df = MagicMock()

        mock_translator_metakg = MagicMock()
        mock_translator_metakg.load_translator_resources.return_value = (
            sample_apinames, sample_metakg, sample_df
        )

        mock_node = MagicMock()
        mock_node.curie = "NCBIGene:3845"
        mock_node.types = ["biolink:Gene"]

        mock_name_resolver = MagicMock()
        mock_name_resolver.lookup.return_value = mock_node

        with patch.dict(sys.modules, {"TCT.translator_metakg": mock_translator_metakg}), \
             patch.object(tct, "name_resolver", mock_name_resolver):
            with pytest.raises(NameError):
                tct.Neighborhood_finder_mcp(
                    "KRAS", node2_categories=["biolink:SmallMolecule"]
                )


# ---------------------------------------------------------------------------
# 10. Neiborhood_finder
# ---------------------------------------------------------------------------

class TestNeiborhoodFinder:
    """Tests for Neiborhood_finder(input_node, node2_categories, resources)."""

    def test_returns_expected_tuple(
        self,
        sample_resources,
        sample_kg_result,
    ):
        # Mock node_normalizer.get_normalized_nodes (receives a single string)
        mock_node = MagicMock()
        mock_node.curie = "NCBIGene:3845"
        mock_node.types = ["biolink:Gene"]

        mock_node_normalizer = MagicMock()
        mock_node_normalizer.get_normalized_nodes.return_value = mock_node

        # Mock translator_query.parallel_api_query to return a KnowledgeGraph
        from TCT.results import KnowledgeGraph, NeighborhoodResult
        mock_translator_query = MagicMock()
        mock_translator_query.parallel_api_query.return_value = KnowledgeGraph(edges=sample_kg_result)

        with patch.dict(sys.modules, {
            "TCT.node_normalizer": mock_node_normalizer,
            "TCT.translator_query": mock_translator_query,
        }), patch("TCT.node_normalizer.convert_ids_to_preferred_names",
                   return_value=["Water", "Water", "Type 2 Diabetes"]):
            result = tct.Neiborhood_finder(
                input_node="NCBIGene:3845",
                node2_categories=["biolink:SmallMolecule"],
                resources=sample_resources,
            )

        # Should return a NeighborhoodResult
        assert isinstance(result, NeighborhoodResult)
        assert result.input_node_id == "NCBIGene:3845"
        assert isinstance(result.knowledge_graph, KnowledgeGraph)
        assert isinstance(result.ranked, pd.DataFrame)


# ---------------------------------------------------------------------------
# 11. Path_finder
# ---------------------------------------------------------------------------

class TestPathFinder:
    """Tests for Path_finder(input_node1, input_node2, intermediate_categories, resources)."""

    def test_returns_expected_tuple(
        self,
        sample_resources,
    ):
        # Mock get_normalized_nodes: receives a list of 2 CURIEs, returns dict
        mock_node1 = MagicMock()
        mock_node1.curie = "NCBIGene:3845"
        mock_node1.types = ["biolink:Gene"]

        mock_node2 = MagicMock()
        mock_node2.curie = "NCBIGene:4869"
        mock_node2.types = ["biolink:Gene"]

        mock_node_normalizer = MagicMock()
        mock_node_normalizer.get_normalized_nodes.return_value = {
            "NCBIGene:3845": mock_node1,
            "NCBIGene:4869": mock_node2,
        }

        # Both parallel_api_query calls return small results with a shared output node.
        result_for_node1 = {
            "edge1": {
                "subject": "NCBIGene:3845",
                "object": "CHEBI:15377",
                "predicate": "biolink:interacts_with",
                "sources": [
                    {"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"},
                ],
            },
        }
        result_for_node2 = {
            "edge1": {
                "subject": "NCBIGene:4869",
                "object": "CHEBI:15377",
                "predicate": "biolink:related_to",
                "sources": [
                    {"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"},
                ],
            },
        }

        from TCT.results import KnowledgeGraph, PathResult
        mock_translator_query = MagicMock()
        mock_translator_query.parallel_api_query.side_effect = [
            KnowledgeGraph(edges=result_for_node1),
            KnowledgeGraph(edges=result_for_node2),
        ]

        with patch.dict(sys.modules, {
            "TCT.node_normalizer": mock_node_normalizer,
            "TCT.translator_query": mock_translator_query,
        }), patch("TCT.node_normalizer.convert_ids_to_preferred_names",
                   return_value=["Water"]), \
             patch.object(tct, "plot_path_bar"):
            result = tct.Path_finder(
                input_node1="NCBIGene:3845",
                input_node2="NCBIGene:4869",
                intermediate_categories=["biolink:SmallMolecule"],
                resources=sample_resources,
            )

        # Should return a PathResult
        assert isinstance(result, PathResult)

        assert result.node1_id == "NCBIGene:3845"
        assert result.node2_id == "NCBIGene:4869"
        assert isinstance(result.knowledge_graph1, KnowledgeGraph)
        assert isinstance(result.knowledge_graph2, KnowledgeGraph)
        assert isinstance(result.ranked1, pd.DataFrame)
        assert isinstance(result.ranked2, pd.DataFrame)
        assert isinstance(result.paths, pd.DataFrame)


# ---------------------------------------------------------------------------
# 12. connecting_two_dots_two_hops
# ---------------------------------------------------------------------------

class TestConnectingTwoDotsTwoHops:
    """Tests for connecting_two_dots_two_hops(sorted_dic1, sorted_dic)."""

    def test_common_gene_appears_in_result(self):
        sorted_dic1 = [("geneA", 5), ("geneB", 3)]
        sorted_dic2 = [("geneB", 4), ("geneC", 2)]

        result = tct.connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)

        assert isinstance(result, pd.DataFrame)
        assert "node" in result.columns
        assert "normalized_rank" in result.columns
        assert "geneB" in result["node"].values

    def test_no_common_genes(self):
        sorted_dic1 = [("geneA", 5), ("geneB", 3)]
        sorted_dic2 = [("geneC", 4), ("geneD", 2)]

        result = tct.connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_multiple_common_genes(self):
        sorted_dic1 = [("geneA", 5), ("geneB", 3), ("geneC", 1)]
        sorted_dic2 = [("geneB", 4), ("geneC", 2), ("geneD", 1)]

        result = tct.connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)

        assert isinstance(result, pd.DataFrame)
        assert "geneB" in result["node"].values
        assert "geneC" in result["node"].values
        # Result should be sorted by normalized_rank ascending
        ranks = result["normalized_rank"].tolist()
        assert ranks == sorted(ranks)
