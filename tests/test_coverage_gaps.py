"""Gap-filling tests to push coverage from 93% to 95%.

Targets:
- server.py: 6 remaining error-path except blocks
- translator_node.py: identifier property getter/setter, categories property, from_dict ValueError
- node_normalizer.py: error paths, unmapped IDs, no-label branches
- name_resolver.py: error response codes, empty results, batch edge cases
- TCT.py: uncovered branches in parse_KG, parse_network_result, ranking functions,
           deprecated functions, visulize_path, TRAPI_json_validation
"""

import pytest
import requests
import pandas as pd
from unittest.mock import patch, MagicMock

from mcp.shared.exceptions import McpError

from TCT.server import (
    add_custom_api_to_metakg,
    add_plover_apis_to_metakg,
    get_api_predicates,
    optimize_query_for_api,
    query_knowledge_provider,
    parallel_query_apis,
)
from TCT.translator_node import TranslatorNode
from TCT.TCT import (
    parse_KG,
    parse_network_result,
    rank_by_primary_infores,
    rank_by_primary_infores_input_as_list,
    query_KP_all,
    visulize_path,
    TRAPI_json_validation,
    get_curie,
)


def test_add_custom_api_to_metakg_error():
    with patch("TCT.server.add_new_API_for_query", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            add_custom_api_to_metakg.fn({}, pd.DataFrame(), "n", "u", "p", "s", "o")


def test_add_plover_apis_to_metakg_error():
    with patch("TCT.server.add_plover_API", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            add_plover_apis_to_metakg.fn({}, pd.DataFrame())


def test_get_api_predicates_error():
    with patch("TCT.server.get_translator_API_predicates", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            get_api_predicates.fn()


def test_optimize_query_for_api_error():
    with patch("TCT.server.optimize_query_json", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            optimize_query_for_api.fn({}, "api", {})


def test_query_knowledge_provider_error():
    with patch("TCT.server.query_KP", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            query_knowledge_provider.fn("api", {}, {}, {})


def test_parallel_query_apis_error():
    with patch("TCT.server.parallel_api_query", side_effect=Exception("fail")):
        with pytest.raises(McpError):
            parallel_query_apis.fn({}, [], {}, {})


# ──────────────────────────────────────────────────────────────────────────────
# 2. translator_node.py — lines 63, 68, 72, 78
# ──────────────────────────────────────────────────────────────────────────────


def test_translator_node_identifier_getter():
    n = TranslatorNode("MONDO:0005148")
    assert n.identifier == "MONDO:0005148"


def test_translator_node_identifier_setter():
    n = TranslatorNode("MONDO:0005148")
    n.identifier = "MONDO:0004979"
    assert n.curie == "MONDO:0004979"
    assert n.identifier == "MONDO:0004979"


def test_translator_node_categories_property():
    n = TranslatorNode("MONDO:0005148")
    n.types = ["biolink:Disease", "biolink:Gene"]
    assert n.categories == ["biolink:Disease", "biolink:Gene"]


def test_translator_node_name_property():
    n = TranslatorNode("MONDO:0005148", label="type 2 diabetes mellitus")
    assert n.name == "type 2 diabetes mellitus"
    assert n.name == n.label


def test_translator_node_from_dict_missing_curie():
    with pytest.raises(ValueError, match="curie"):
        TranslatorNode.from_dict({"label": "test"})


# ──────────────────────────────────────────────────────────────────────────────
# 3. node_normalizer.py — error paths and edge cases
# ──────────────────────────────────────────────────────────────────────────────

class TestNodeNormalizerErrorPaths:
    """Cover lines 93, 120-121, 125-126, 129, 167, 181-186, 188."""

    @patch("TCT.node_normalizer.requests.post")
    def test_get_normalized_nodes_non_200_raises(self, mock_post):
        """Line 93: raise RequestException on non-200."""
        mock_post.return_value = MagicMock(status_code=500)
        import TCT.node_normalizer as nn
        with pytest.raises(requests.RequestException):
            nn.get_normalized_nodes("BAD:ID", mode="post")

    @patch("TCT.node_normalizer.get_normalized_nodes")
    def test_get_preferred_names_unmapped_id(self, mock_norm):
        """Lines 120-121, 129: curie not in normalized_nodes → unmapped."""
        mock_norm.return_value = {"GOOD:1": MagicMock(label="GoodName"), "BAD:1": None}
        import TCT.node_normalizer as nn
        result = nn.get_preferred_names(["GOOD:1", "BAD:1"])
        assert result["GOOD:1"] == "GoodName"
        assert result["BAD:1"] == "BAD:1"  # unmapped returns itself

    @patch("TCT.node_normalizer.get_normalized_nodes")
    def test_get_preferred_names_no_label(self, mock_norm):
        """Lines 125-126: label is None → uses curie as fallback."""
        node = MagicMock()
        node.label = None
        mock_norm.return_value = {"ID:1": node}
        import TCT.node_normalizer as nn
        result = nn.get_preferred_names(["ID:1"])
        assert result["ID:1"] == "ID:1"

    @patch("TCT.node_normalizer.get_normalized_nodes")
    def test_get_preferred_names_and_categories(self, mock_norm):
        """Combined resolver returns both name and category maps in one pass."""
        mock_norm.return_value = {
            "NCBIGene:3845": TranslatorNode("NCBIGene:3845", label="KRAS", types=["biolink:Gene"]),
            "NOLABEL:1": TranslatorNode("NOLABEL:1", label=None, types=["biolink:NamedThing"]),
            "BAD:1": None,
        }
        import TCT.node_normalizer as nn
        names, categories = nn.get_preferred_names_and_categories(
            ["NCBIGene:3845", "NOLABEL:1", "BAD:1"]
        )
        assert names == {"NCBIGene:3845": "KRAS", "NOLABEL:1": "NOLABEL:1", "BAD:1": "BAD:1"}
        assert categories == {
            "NCBIGene:3845": ["biolink:Gene"],
            "NOLABEL:1": ["biolink:NamedThing"],
            "BAD:1": None,
        }

    @patch("TCT.node_normalizer.requests.post")
    def test_id_convert_non_200_raises(self, mock_post):
        """Non-200 response raises an exception."""
        mock_post.return_value = MagicMock(ok=False, status_code=500)
        import TCT.node_normalizer as nn
        with pytest.raises(Exception, match="[Ee]rror"):
            nn.ID_convert_to_preferred_name_nodeNormalizer(["ID:1"])

    @patch("TCT.node_normalizer.requests.post")
    @patch("TCT.node_normalizer.requests.get")
    def test_id_convert_no_label_and_unrecognized(self, mock_get, mock_post):
        """No label → curie fallback; unrecognized curies."""
        mock_resp = MagicMock(ok=True, status_code=200)
        mock_resp.json.return_value = {
            "KNOWN:1": {
                "id": {"identifier": "KNOWN:NORM", "label": None},
                "type": [],
            },
            "UNKNOWN:1": None,
        }
        mock_post.return_value = mock_resp
        mock_get.return_value = mock_resp
        import TCT.node_normalizer as nn
        result = nn.ID_convert_to_preferred_name_nodeNormalizer(["KNOWN:1", "UNKNOWN:1"])
        assert result["KNOWN:1"] == "KNOWN:1"  # no label → curie
        assert result["UNKNOWN:1"] == "UNKNOWN:1"  # unrecognized


# ──────────────────────────────────────────────────────────────────────────────
# 4. name_resolver.py — error paths
# ──────────────────────────────────────────────────────────────────────────────

class TestNameResolverErrorPaths:
    """Cover lines 72, 96, 107, 157, 169-173."""

    @patch("TCT.name_resolver.requests.get")
    def test_lookup_non_200_raises(self, mock_get):
        """Line 72: non-200 response raises RequestException."""
        mock_get.return_value = MagicMock(status_code=500)
        import TCT.name_resolver as nr
        with pytest.raises(requests.RequestException):
            nr.lookup("anything")

    @patch("TCT.name_resolver.requests.get")
    def test_synonyms_empty_result_raises(self, mock_get):
        """Line 96: empty result raises LookupError."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp
        import TCT.name_resolver as nr
        with pytest.raises(LookupError):
            nr.synonyms("CURIE:EMPTY")

    @patch("TCT.name_resolver.requests.get")
    def test_synonyms_non_200_raises(self, mock_get):
        """Line 107: non-200 response raises RequestException."""
        mock_get.return_value = MagicMock(status_code=500)
        import TCT.name_resolver as nr
        with pytest.raises(requests.RequestException):
            nr.synonyms("CURIE:BAD")

    @patch("TCT.name_resolver.requests.post")
    def test_batch_lookup_empty_raises(self, mock_post):
        """Line 157: empty batch result raises LookupError."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp
        import TCT.name_resolver as nr
        with pytest.raises(LookupError):
            nr.batch_lookup(["empty_query"])

    @patch("TCT.name_resolver.requests.post")
    def test_batch_lookup_non_200_raises(self, mock_post):
        """Line 173: non-200 raises RequestException."""
        mock_post.return_value = MagicMock(status_code=500)
        import TCT.name_resolver as nr
        with pytest.raises(requests.RequestException):
            nr.batch_lookup(["anything"])

    @patch("TCT.name_resolver.requests.post")
    def test_batch_lookup_no_top_response_returns_list(self, mock_post):
        """Lines 169-171: return_top_response=False returns list, and None for empty."""
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {
            "present": [{"curie": "ID:1", "label": "Name1", "types": ["biolink:Gene"]}],
            "empty": [],
        }
        mock_post.return_value = mock_resp
        import TCT.name_resolver as nr
        result = nr.batch_lookup(["present", "empty"], return_top_response=False)
        assert isinstance(result["present"], list)
        assert len(result["present"]) == 1


# ──────────────────────────────────────────────────────────────────────────────
# 5. TCT.py — uncovered branches
# ──────────────────────────────────────────────────────────────────────────────


class TestParseKGExistingKeyAggregator:
    """Cover lines 1149-1153: existing key + aggregator_knowledge_source branch."""

    def test_existing_key_with_aggregator(self):
        """When the same subject-object pair appears in multiple edges, the second
        edge exercises the existing-key branch. If the second edge has an
        aggregator_knowledge_source AND the key already exists, it hits the append
        branch (line 1152)."""
        kg = {
            "edge1": {
                "subject": "A",
                "object": "B",
                "predicate": "biolink:interacts_with",
                "sources": [
                    {"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"},
                    {"resource_id": "infores:agg1", "resource_role": "aggregator_knowledge_source"},
                ],
                "attributes": [],
            },
            "edge2": {
                "subject": "A",
                "object": "B",
                "predicate": "biolink:related_to",
                "sources": [
                    {"resource_id": "infores:kp2", "resource_role": "primary_knowledge_source"},
                    {"resource_id": "infores:agg2", "resource_role": "aggregator_knowledge_source"},
                ],
                "attributes": [],
            },
        }
        result = parse_KG(kg)
        key = "A_B"
        assert key in result
        assert len(result[key]["predicate"]) == 2
        assert len(result[key]["aggregator_knowledge_source"]) == 2


class TestParseNetworkResultBranches:
    """Cover lines 1196, 1209-1210, 1224-1225 in parse_network_result."""

    def test_network_with_shared_nodes(self):
        """Cover the join/filter branches in parse_network_result.
        Need multiple input nodes so that a shared intermediate connects to >1 input."""
        result = {
            "e1": {"subject": "INPUT1", "object": "A", "predicate": "p1",
                   "sources": [{"resource_id": "kp1", "resource_role": "primary_knowledge_source"}]},
            "e2": {"subject": "INPUT2", "object": "A", "predicate": "p2",
                   "sources": [{"resource_id": "kp2", "resource_role": "primary_knowledge_source"}]},
            "e3": {"subject": "INPUT1", "object": "B", "predicate": "p3",
                   "sources": [{"resource_id": "kp3", "resource_role": "primary_knowledge_source"}]},
            "e4": {"subject": "INPUT2", "object": "B", "predicate": "p4",
                   "sources": [{"resource_id": "kp4", "resource_role": "primary_knowledge_source"}]},
        }
        # A and B each connect to both INPUT1 and INPUT2 → covers lines 1196, 1209-1210, 1224-1225
        input_node1_list = ["INPUT1", "INPUT2"]
        parsed_result = parse_network_result(result, input_node1_list)
        assert isinstance(parsed_result, pd.DataFrame)
        assert len(parsed_result) > 0


class TestRankByPrimaryInforesInputAsListElseBranch:
    """Cover lines 1252-1258, 1268 (object in input_nodes, else append item)."""

    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_object_in_input_nodes(self, mock_id):
        """When the object is the input node, it covers the elif branch at line 1252."""
        mock_id.return_value = {}  # empty → hits else at line 1268
        result_parsed = {
            "INPUT_X": {
                "subject": "A",
                "object": "INPUT",
                "predicate": ["biolink:affects"],
                "primary_knowledge_source": ["infores:kp1"],
                "evidence": ["ev1"],
            },
        }
        df = rank_by_primary_infores_input_as_list(result_parsed, ["INPUT"])
        assert isinstance(df, pd.DataFrame)


class TestRankByPrimaryInforesElseBranch:
    """Cover line 1319 (else append item when item NOT in dic_id_map)."""

    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_unmapped_item(self, mock_id):
        mock_id.return_value = {}  # empty → all items hit else branch
        result_parsed = {
            "INPUT_B": {
                "subject": "INPUT",
                "object": "B",
                "predicate": ["biolink:affects"],
                "primary_knowledge_source": ["infores:kp1"],
                "evidence": ["ev1"],
            },
        }
        df = rank_by_primary_infores(result_parsed, "INPUT")
        assert isinstance(df, pd.DataFrame)
        assert "Name" in df.columns


class TestDeprecatedParseResultOldBranches:
    """Cover lines 1518, 1530, 1541-1543, 1548-1554, 1572, 1575, 1591, 1595, 1621."""

    @patch("TCT.TCT.select_predicates_inKP")
    @patch("TCT.TCT.format_query_json")
    def test_query_kp_all_with_api_list_and_no_predicates(self, mock_format, mock_sele_pred):
        """Lines 1518, 1530: non-empty API_list → uses apinames.keys(); empty predicates → calls select_predicates_inKP."""
        mock_format.return_value = {"message": {}}
        mock_sele_pred.return_value = ["biolink:treats"]
        metakg = pd.DataFrame({
            "API": ["API_A"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Disease"],
            "Predicate": ["biolink:treats"],
            "URL": ["http://example.com"],
        })
        apinames = {"API_A": "http://example.com"}
        # Non-empty API_list with items triggers line 1518
        result_dict, result_concept = query_KP_all(
            ["NCBIGene:3845"], [], ["biolink:Gene"], ["biolink:Disease"],
            [], ["API_A"], metakg, apinames
        )
        assert isinstance(result_dict, dict)
        mock_sele_pred.assert_called_once()


class TestGetCurieEdgeCases:
    """Cover line 1483: empty result returns original name."""

    @patch("TCT.TCT.requests.post")
    def test_200_empty_result_returns_name(self, mock_post):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp
        result = get_curie("unknown_thing")
        assert result == "unknown_thing"

    @patch("TCT.TCT.requests.post")
    def test_non_200_returns_name(self, mock_post):
        mock_post.return_value = MagicMock(status_code=500)
        result = get_curie("bad_query")
        assert result == "bad_query"


class TestVisulizePathElseBranches:
    """Cover lines 2134, 2141, 2160-2161 in visulize_path."""

    @patch("TCT.visualization.display")
    @patch("TCT.visualization.ipycytoscape")
    @patch("TCT.visualization.ID_convert_to_preferred_name_nodeNormalizer")
    def test_unmapped_items_and_dedup(self, mock_id, mock_cyto, mock_display):
        """Items not in dic_id_map hit else branches (lines 2134, 2141).
        Duplicate check1==check2 pairs hit lines 2160-2161."""
        mock_id.return_value = {}  # empty → all items hit else
        mock_cyto.CytoscapeWidget.return_value = MagicMock()

        # visulize_path(input_node1_id, intermediate_node, input_node3_id, result, result2)
        # result/result2 are raw KG edge dicts (not parsed)
        result = {
            "e1": {
                "subject": "NODE1",
                "object": "MID",
                "predicate": "biolink:interacts_with",
                "sources": [{"resource_id": "infores:kp1"}],
            },
            "e2": {
                "subject": "MID",
                "object": "NODE1",
                "predicate": "biolink:interacts_with",
                "sources": [{"resource_id": "infores:kp1"}],
            },
        }
        result2 = {
            "e3": {
                "subject": "NODE3",
                "object": "MID",
                "predicate": "biolink:affects",
                "sources": [{"resource_id": "infores:kp2"}],
            },
        }
        visulize_path("NODE1", "MID", "NODE3", result, result2)
        mock_display.assert_called_once()


class TestTRAPIJsonValidationMissingN1Categories:
    """Cover line 2011: n1 present but missing categories."""

    def test_n1_missing_categories(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {
                        "n0": {"categories": ["biolink:Gene"]},
                        "n1": {},
                    },
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], ["biolink:Gene"])
        out = capsys.readouterr().out
        assert "categories is missing" in out
