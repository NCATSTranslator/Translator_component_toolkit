import pandas as pd
from unittest.mock import patch, MagicMock

from TCT.translator_query import (
    get_translator_API_predicates,
    optimize_query_json,
    query_KP,
    parallel_api_query,
)
from TCT.translator_resources import TranslatorResources


# ---------------------------------------------------------------------------
# get_translator_API_predicates tests
# ---------------------------------------------------------------------------

class TestGetTranslatorAPIPredicates:
    """Tests for get_translator_API_predicates with mocked upstream calls."""

    @patch("TCT.translator_query.translator_metakg.add_plover_API")
    @patch("TCT.translator_query.translator_metakg.get_KP_metadata")
    @patch("TCT.translator_query.translator_kpinfo.get_translator_kp_info")
    def test_returns_tuple_of_dict_df_dict(
        self, mock_kp_info, mock_kp_metadata, mock_plover
    ):
        """Returns a tuple of (dict, DataFrame, dict)."""
        mock_df = pd.DataFrame({
            "id": ["id1"],
            "title": ["API1"],
            "prod_url": ["https://example.com"],
            "ci_url": [None],
            "test_url": [None],
        })
        mock_api_names = {"API1": "https://example.com/query"}
        mock_kp_info.return_value = (mock_df, mock_api_names)

        mock_meta_kg = pd.DataFrame({
            "API": ["API1"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Gene"],
            "URL": ["https://example.com/query"],
        })
        mock_kp_metadata.return_value = mock_meta_kg
        mock_plover.return_value = (mock_api_names, mock_meta_kg)

        result = get_translator_API_predicates()

        assert isinstance(result, TranslatorResources)
        assert isinstance(result.api_names, dict)
        assert isinstance(result.meta_kg, pd.DataFrame)
        assert isinstance(result.api_predicates, dict)
        assert "API1" in result.api_predicates
        assert "biolink:interacts_with" in result.api_predicates["API1"]


# ---------------------------------------------------------------------------
# optimize_query_json tests
# ---------------------------------------------------------------------------

class TestOptimizeQueryJson:
    """Tests for optimize_query_json."""

    def test_shared_predicates(self):
        """When there are shared predicates, they replace the original list."""
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": [
                                "biolink:interacts_with",
                                "biolink:related_to",
                                "biolink:treats",
                            ],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }
        api_predicates = {
            "TestAPI": ["biolink:interacts_with", "biolink:affects"],
        }

        result = optimize_query_json(query_json, "TestAPI", api_predicates)

        result_predicates = result["message"]["query_graph"]["edges"]["e00"]["predicates"]
        assert result_predicates == ["biolink:interacts_with"]

    def test_no_shared_predicates(self):
        """When there are no shared predicates, keep the original predicates."""
        original_predicates = ["biolink:related_to", "biolink:treats"]
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": original_predicates[:],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }
        api_predicates = {
            "TestAPI": ["biolink:affects"],
        }

        result = optimize_query_json(query_json, "TestAPI", api_predicates)

        result_predicates = result["message"]["query_graph"]["edges"]["e00"]["predicates"]
        assert set(result_predicates) == set(original_predicates)


# ---------------------------------------------------------------------------
# query_KP tests
# ---------------------------------------------------------------------------

class TestQueryKP:
    """Tests for query_KP with mocked HTTP calls."""

    @patch("TCT.translator_query.requests.post")
    def test_200_with_edges_returns_result(self, mock_post):
        """200 response with edges returns the result dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "knowledge_graph": {
                    "edges": {"e1": {"subject": "A", "object": "B"}},
                }
            }
        }
        mock_post.return_value = mock_response

        resources = TranslatorResources(
            api_names={"TestAPI": "https://example.com/query"},
            meta_kg=pd.DataFrame(),
            api_predicates={"TestAPI": ["biolink:interacts_with"]},
        )
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": ["biolink:interacts_with"],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }

        result = query_KP("TestAPI", query_json, resources)

        assert result is not None
        assert "knowledge_graph" in result
        assert "edges" in result["knowledge_graph"]
        assert "e1" in result["knowledge_graph"]["edges"]

    @patch("TCT.translator_query.requests.post")
    def test_200_with_empty_edges_returns_none(self, mock_post):
        """200 response with empty edges returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {
                "knowledge_graph": {
                    "edges": {},
                }
            }
        }
        mock_post.return_value = mock_response

        resources = TranslatorResources(
            api_names={"TestAPI": "https://example.com/query"},
            meta_kg=pd.DataFrame(),
            api_predicates={"TestAPI": ["biolink:interacts_with"]},
        )
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": ["biolink:interacts_with"],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }

        result = query_KP("TestAPI", query_json, resources)
        assert result is None

    @patch("TCT.translator_query.requests.post")
    def test_non_200_returns_none(self, mock_post):
        """Non-200 response returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        resources = TranslatorResources(
            api_names={"TestAPI": "https://example.com/query"},
            meta_kg=pd.DataFrame(),
            api_predicates={"TestAPI": ["biolink:interacts_with"]},
        )
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": ["biolink:interacts_with"],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }

        result = query_KP("TestAPI", query_json, resources)
        assert result is None


# ---------------------------------------------------------------------------
# parallel_api_query tests
# ---------------------------------------------------------------------------

class TestParallelApiQuery:
    """Tests for parallel_api_query with mocked query_KP."""

    @patch("TCT.translator_query.query_KP")
    def test_merges_results_from_successful_apis(self, mock_query_kp):
        """Results from successful APIs are merged; None results are excluded."""

        def side_effect(api_name, query_json, resources):
            if api_name == "API_A":
                return {
                    "knowledge_graph": {
                        "edges": {"e1": {"subject": "A", "object": "B"}}
                    }
                }
            elif api_name == "API_B":
                return {
                    "knowledge_graph": {
                        "edges": {"e2": {"subject": "C", "object": "D"}}
                    }
                }
            else:
                # API_C returns None
                return None

        mock_query_kp.side_effect = side_effect

        api_names = {
            "API_A": "https://api-a.example.com/query",
            "API_B": "https://api-b.example.com/query",
            "API_C": "https://api-c.example.com/query",
        }
        api_predicates = {
            "API_A": ["biolink:interacts_with"],
            "API_B": ["biolink:related_to"],
            "API_C": ["biolink:affects"],
        }
        query_json = {
            "message": {
                "query_graph": {
                    "edges": {
                        "e00": {
                            "subject": "n00",
                            "object": "n01",
                            "predicates": ["biolink:interacts_with"],
                        }
                    },
                    "nodes": {
                        "n00": {"ids": ["NCBIGene:3845"]},
                        "n01": {"categories": ["biolink:Gene"]},
                    },
                }
            }
        }
        select_apis = ["API_A", "API_B", "API_C"]

        resources = TranslatorResources(
            api_names=api_names,
            meta_kg=pd.DataFrame(),
            api_predicates=api_predicates,
        )
        result = parallel_api_query(
            query_json, select_apis, resources, max_workers=2
        )

        # Merged dict should contain edges from API_A and API_B
        assert "e1" in result
        assert "e2" in result
        assert result["e1"]["subject"] == "A"
        assert result["e2"]["subject"] == "C"
