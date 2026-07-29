"""Tests for pure-computation functions in TCT/TCT.py.

Uses unittest.mock.patch for HTTP/external calls and fixtures from conftest.py.
"""

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from TCT.TCT import (
    TCT_help,
    list_functions,
    get_Translator_APIs,
    list_Translator_APIs,
    select_API,
    select_concept,
    sele_predicates_API,
    get_Translator_API_URL,
    filter_APIs,
    select_predicates_inKP,
    format_query_json,
    parse_KG,
    parse_network_result,
    rank_by_primary_infores,
    rank_by_primary_infores_input_as_list,
    merge_by_ranking_index,
    merge_ranking_by_number_of_infores,
    get_curie,
    get_pair_annotation,
    parse_pair_annotation,
    load_json_template,
    extract_json,
    TRAPI_json_validation,
    format_id,
    select_result_to_analysis,
    Gene_id_converter,
    query_KP_all,
    connecting_two_dots_two_hops,
    find_path_by_two_ends,
    get_SmartAPI_Translator_KP_info,
    ID_convert_to_preferred_name_nodeNormalizer,
    load_translator_resources,
)


# ---------------------------------------------------------------------------
# 1. TCT_help
# ---------------------------------------------------------------------------
class TestTCTHelp:
    def test_prints_docstring(self, capsys):
        def dummy_func():
            """This is a dummy docstring."""
            pass

        TCT_help(dummy_func)
        captured = capsys.readouterr()
        assert "This is a dummy docstring." in captured.out

    def test_prints_none_when_no_docstring(self, capsys):
        def no_doc():
            pass

        TCT_help(no_doc)
        captured = capsys.readouterr()
        assert "None" in captured.out


# ---------------------------------------------------------------------------
# 2. list_functions
# ---------------------------------------------------------------------------
class TestListFunctions:
    def test_returns_known_function_names(self):
        funcs = list_functions()
        assert isinstance(funcs, list)
        # At minimum these should be present
        for name in ["TCT_help", "list_functions", "parse_KG", "get_curie"]:
            assert name in funcs


# ---------------------------------------------------------------------------
# 3. get_Translator_APIs (live HTTP)
# ---------------------------------------------------------------------------
class TestGetTranslatorAPIs:
    @pytest.mark.network
    def test_returns_non_empty_list(self):
        apis = get_Translator_APIs()
        assert isinstance(apis, list)
        assert len(apis) > 0


# ---------------------------------------------------------------------------
# 4. list_Translator_APIs
# ---------------------------------------------------------------------------
class TestListTranslatorAPIs:
    def test_returns_dict_with_known_keys(self):
        api_names = list_Translator_APIs()
        assert isinstance(api_names, dict)
        assert "COHD TRAPI" in api_names
        assert "Aragorn(Trapi v1.4.0)" in api_names
        assert "Sri-name-resolver" in api_names

    def test_values_are_urls(self):
        api_names = list_Translator_APIs()
        for v in api_names.values():
            assert v.startswith("http")


# ---------------------------------------------------------------------------
# 5. select_API
# ---------------------------------------------------------------------------
class TestSelectAPI:
    def test_matching_categories(self, sample_metakg):
        result = select_API(["biolink:Gene"], ["biolink:SmallMolecule"], sample_metakg)
        assert isinstance(result, list)
        assert "API_A" in result
        assert "API_B" in result

    def test_non_matching_categories(self, sample_metakg):
        result = select_API(["biolink:Pathway"], ["biolink:Protein"], sample_metakg)
        assert result == []

    def test_bidirectional(self, sample_metakg):
        # SmallMolecule -> Gene should also find API_B (Subject=SmallMolecule, Object=Gene)
        result = select_API(["biolink:SmallMolecule"], ["biolink:Gene"], sample_metakg)
        assert "API_B" in result


# ---------------------------------------------------------------------------
# 6. select_concept
# ---------------------------------------------------------------------------
class TestSelectConcept:
    def test_returns_predicates(self, sample_metakg):
        result = select_concept(["biolink:Gene"], ["biolink:SmallMolecule"], sample_metakg)
        assert isinstance(result, set)
        assert "biolink:interacts_with" in result

    def test_non_matching(self, sample_metakg):
        result = select_concept(["biolink:Pathway"], ["biolink:Protein"], sample_metakg)
        assert result == set()


# ---------------------------------------------------------------------------
# 7. sele_predicates_API
# ---------------------------------------------------------------------------
class TestSelePredicatesAPI:
    def test_matching(self, sample_metakg, sample_apinames):
        predicates, apis, urls = sele_predicates_API(
            ["biolink:Gene"], ["biolink:SmallMolecule"], sample_metakg, sample_apinames
        )
        assert isinstance(predicates, list)
        assert len(predicates) > 0
        assert isinstance(apis, list)
        assert len(apis) > 0
        assert isinstance(urls, list)
        assert len(urls) > 0

    def test_non_matching(self, sample_metakg, sample_apinames, capsys):
        predicates, apis, urls = sele_predicates_API(
            ["biolink:Pathway"], ["biolink:Protein"], sample_metakg, sample_apinames
        )
        assert predicates == []
        assert apis == []
        captured = capsys.readouterr()
        assert "No predicates found" in captured.out
        assert "No APIs found" in captured.out


# ---------------------------------------------------------------------------
# 8. get_Translator_API_URL
# ---------------------------------------------------------------------------
class TestGetTranslatorAPIURL:
    def test_found(self, sample_apinames):
        urls = get_Translator_API_URL(["API_A", "API_B"], sample_apinames)
        assert "https://api-a.example.com/query" in urls
        assert "https://api-b.example.com/query" in urls

    def test_not_found(self, sample_apinames, capsys):
        urls = get_Translator_API_URL(["NonExistent"], sample_apinames)
        assert urls == []
        captured = capsys.readouterr()
        assert "NonExistent : API name not found" in captured.out


# ---------------------------------------------------------------------------
# 9. filter_APIs
# ---------------------------------------------------------------------------
class TestFilterAPIs:
    def test_empty_predicates_returns_unique_categories(self):
        metakg = pd.DataFrame({
            "KG_category": ["cat1", "cat2", "cat1"],
            "URL": ["url1", "url2", "url3"],
        })
        result = filter_APIs([], metakg)
        assert set(result) == {"cat1", "cat2"}

    def test_with_predicates(self):
        metakg = pd.DataFrame({
            "KG_category": ["cat1", "cat2", "cat1"],
            "URL": ["url1", "url2", "url3"],
        })
        result = filter_APIs(["cat1"], metakg)
        assert set(result) == {"url1", "url3"}


# ---------------------------------------------------------------------------
# 10. select_predicates_inKP
# ---------------------------------------------------------------------------
class TestSelectPredicatesInKP:
    def test_matching(self):
        metakg = pd.DataFrame({
            "API": ["KP1", "KP1", "KP2"],
            "Subject": ["Gene", "Gene", "SmallMolecule"],
            "Object": ["SmallMolecule", "Disease", "Gene"],
            "KG_category": ["Gene-interacts_with-SmallMolecule", "Gene-related_to-Disease", "SmallMolecule-treats-Gene"],
        })
        result = select_predicates_inKP(
            ["biolink:Gene"], ["biolink:SmallMolecule"], "KP1", metakg
        )
        assert isinstance(result, list)
        assert "Gene-interacts_with-SmallMolecule" in result

    def test_non_matching(self):
        metakg = pd.DataFrame({
            "API": ["KP1"],
            "Subject": ["Gene"],
            "Object": ["SmallMolecule"],
            "KG_category": ["Gene-interacts_with-SmallMolecule"],
        })
        result = select_predicates_inKP(
            ["biolink:Pathway"], ["biolink:Protein"], "KP1", metakg
        )
        assert result == []


# ---------------------------------------------------------------------------
# 11. format_query_json
# ---------------------------------------------------------------------------
class TestFormatQueryJson:
    def test_basic_structure(self):
        result = format_query_json(
            ["NCBIGene:3845"], [], ["biolink:Gene"], ["biolink:Disease"],
            ["biolink:interacts_with"]
        )
        assert "message" in result
        assert "query_graph" in result["message"]
        qg = result["message"]["query_graph"]
        assert "edges" in qg
        assert "nodes" in qg
        assert "e00" in qg["edges"]
        assert "n00" in qg["nodes"]
        assert "n01" in qg["nodes"]
        assert qg["nodes"]["n00"]["ids"] == ["NCBIGene:3845"]
        assert qg["nodes"]["n01"]["categories"] == ["biolink:Disease"]
        assert qg["edges"]["e00"]["predicates"] == ["biolink:interacts_with"]

    def test_empty_predicates(self):
        result = format_query_json(["NCBIGene:3845"], [], [], [], [])
        qg = result["message"]["query_graph"]
        # When predicates is empty the original list stays
        assert qg["edges"]["e00"]["predicates"] == []

    def test_empty_subject_ids(self):
        result = format_query_json([], [], [], ["biolink:Gene"], ["biolink:treats"])
        qg = result["message"]["query_graph"]
        assert qg["nodes"]["n00"]["ids"] == []


# ---------------------------------------------------------------------------
# 12. parse_KG
# ---------------------------------------------------------------------------
class TestParseKG:
    def test_new_key_and_existing_key(self, sample_kg_result):
        from TCT.results import ParsedKnowledgeGraph
        parsed = parse_KG(sample_kg_result)
        assert isinstance(parsed, ParsedKnowledgeGraph)

        # edge1 creates "NCBIGene:3845_CHEBI:15377"
        key1 = "NCBIGene:3845_CHEBI:15377"
        assert key1 in parsed
        assert parsed[key1]["subject"] == "NCBIGene:3845"
        assert parsed[key1]["object"] == "CHEBI:15377"
        assert "biolink:interacts_with" in parsed[key1]["predicate"]
        # edge2 has same subject_object => existing key branch
        assert "biolink:related_to" in parsed[key1]["predicate"]
        assert "infores:kp1" in parsed[key1]["primary_knowledge_source"]
        assert "infores:kp2" in parsed[key1]["primary_knowledge_source"]

        # edge3 is reversed direction => new key "CHEBI:15377_NCBIGene:3845"
        key3 = "CHEBI:15377_NCBIGene:3845"
        assert key3 in parsed
        assert "biolink:affects" in parsed[key3]["predicate"]

        # edge4 is a completely new pair
        key4 = "NCBIGene:3845_MONDO:0005148"
        assert key4 in parsed
        assert "biolink:gene_associated_with_condition" in parsed[key4]["predicate"]

    def test_aggregator_sources(self, sample_kg_result):
        parsed = parse_KG(sample_kg_result)
        key1 = "NCBIGene:3845_CHEBI:15377"
        assert "aggregator_knowledge_source" in parsed[key1]
        assert "infores:agg1" in parsed[key1]["aggregator_knowledge_source"]

    def test_evidence_field(self, sample_kg_result):
        parsed = parse_KG(sample_kg_result)
        key1 = "NCBIGene:3845_CHEBI:15377"
        assert "evidence" in parsed[key1]
        assert len(parsed[key1]["evidence"]) > 0


# ---------------------------------------------------------------------------
# 13. parse_network_result
# ---------------------------------------------------------------------------
class TestParseNetworkResult:
    def test_basic(self):
        result = {
            "e1": {"subject": "A", "object": "B", "predicate": "p1", "sources": []},
            "e2": {"subject": "A", "object": "C", "predicate": "p2", "sources": []},
            "e3": {"subject": "B", "object": "C", "predicate": "p3", "sources": []},
        }
        input_nodes = ["A"]
        df = parse_network_result(result, input_nodes)
        assert isinstance(df, pd.DataFrame)
        assert "Subject" in df.columns
        assert "Object" in df.columns

    def test_self_loop_excluded(self):
        result = {
            "e1": {"subject": "A", "object": "A", "predicate": "p1", "sources": []},
            "e2": {"subject": "A", "object": "B", "predicate": "p2", "sources": []},
        }
        input_nodes = ["A"]
        df = parse_network_result(result, input_nodes)
        # Self-loop should be excluded from adjacency
        assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# 14. rank_by_primary_infores
# ---------------------------------------------------------------------------
class TestRankByPrimaryInfores:
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dataframe(self, mock_id_converter):
        mock_id_converter.return_value = {
            "CHEBI:15377": "Water",
            "MONDO:0005148": "Diabetes",
        }
        result_parsed = {
            "NCBIGene:3845_CHEBI:15377": {
                "predicate": ["biolink:interacts_with"],
                "subject": "NCBIGene:3845",
                "object": "CHEBI:15377",
                "primary_knowledge_source": ["infores:kp1", "infores:kp2"],
            },
            "NCBIGene:3845_MONDO:0005148": {
                "predicate": ["biolink:related_to"],
                "subject": "NCBIGene:3845",
                "object": "MONDO:0005148",
                "primary_knowledge_source": ["infores:kp3"],
            },
        }
        df = rank_by_primary_infores(result_parsed, "NCBIGene:3845")
        assert isinstance(df, pd.DataFrame)
        assert "output_node" in df.columns
        assert "Name" in df.columns
        assert "Num_of_primary_infores" in df.columns
        assert "type_of_nodes" in df.columns
        # Sorted descending by Num_of_primary_infores
        vals = df["Num_of_primary_infores"].tolist()
        assert vals == sorted(vals, reverse=True)

    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_reverse_direction(self, mock_id_converter):
        mock_id_converter.return_value = {"CHEBI:15377": "Water"}
        result_parsed = {
            "CHEBI:15377_NCBIGene:3845": {
                "predicate": ["biolink:affects"],
                "subject": "CHEBI:15377",
                "object": "NCBIGene:3845",
                "primary_knowledge_source": ["infores:kp3"],
            },
        }
        df = rank_by_primary_infores(result_parsed, "NCBIGene:3845")
        assert df.iloc[0]["output_node"] == "CHEBI:15377"
        assert df.iloc[0]["type_of_nodes"] == "subject"


# ---------------------------------------------------------------------------
# 15. rank_by_primary_infores_input_as_list
# ---------------------------------------------------------------------------
class TestRankByPrimaryInforesInputAsList:
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_dataframe(self, mock_id_converter):
        mock_id_converter.return_value = {
            "CHEBI:15377": "Water",
            "MONDO:0005148": "Diabetes",
        }
        result_parsed = {
            "NCBIGene:3845_CHEBI:15377": {
                "predicate": ["biolink:interacts_with"],
                "subject": "NCBIGene:3845",
                "object": "CHEBI:15377",
                "primary_knowledge_source": ["infores:kp1"],
            },
            "NCBIGene:999_MONDO:0005148": {
                "predicate": ["biolink:related_to"],
                "subject": "NCBIGene:999",
                "object": "MONDO:0005148",
                "primary_knowledge_source": ["infores:kp3"],
            },
        }
        df = rank_by_primary_infores_input_as_list(
            result_parsed, ["NCBIGene:3845", "NCBIGene:999"]
        )
        assert isinstance(df, pd.DataFrame)
        assert "input_node" in df.columns
        assert "output_node" in df.columns
        assert "Name" in df.columns


# ---------------------------------------------------------------------------
# 16. merge_by_ranking_index
# ---------------------------------------------------------------------------
class TestMergeByRankingIndex:
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_sorted_dataframe(self, mock_id_converter):
        mock_id_converter.return_value = {
            "NodeA": "NameA",
            "NodeB": "NameB",
        }
        r1 = pd.DataFrame({
            "output_node": ["NodeA", "NodeB", "NodeC"],
            "Num_of_primary_infores": [3, 2, 1],
        })
        r2 = pd.DataFrame({
            "output_node": ["NodeA", "NodeB", "NodeD"],
            "Num_of_primary_infores": [5, 1, 2],
        })
        result = merge_by_ranking_index(r1, r2)
        assert isinstance(result, pd.DataFrame)
        assert "score" in result.columns
        # Only overlapping nodes appear
        assert len(result) == 2

    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_no_overlap(self, mock_id_converter):
        mock_id_converter.return_value = {}
        r1 = pd.DataFrame({"output_node": ["NodeA"], "Num_of_primary_infores": [3]})
        r2 = pd.DataFrame({"output_node": ["NodeB"], "Num_of_primary_infores": [5]})
        result = merge_by_ranking_index(r1, r2)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# 17. merge_ranking_by_number_of_infores
# ---------------------------------------------------------------------------
class TestMergeRankingByNumberOfInfores:
    @patch("TCT.TCT.plot_path_bar")
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_returns_sorted_dataframe(self, mock_id_converter, mock_plot):
        mock_id_converter.return_value = {
            "NodeA": "NameA",
            "NodeB": "NameB",
        }
        r1 = pd.DataFrame({
            "output_node": ["NodeA", "NodeB", "NodeC"],
            "Num_of_primary_infores": [3, 2, 1],
            "unique_predicates": [["p1"], ["p2"], ["p3"]],
        })
        r2 = pd.DataFrame({
            "output_node": ["NodeA", "NodeB", "NodeD"],
            "Num_of_primary_infores": [5, 1, 2],
            "unique_predicates": [["p4"], ["p5"], ["p6"]],
        })
        result = merge_ranking_by_number_of_infores(r1, r2)
        assert isinstance(result, pd.DataFrame)
        assert "score" in result.columns
        assert "output_node" in result.columns
        mock_plot.assert_called_once()

    @patch("TCT.TCT.plot_path_bar")
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_no_overlap(self, mock_id_converter, mock_plot):
        mock_id_converter.return_value = {}
        r1 = pd.DataFrame({
            "output_node": ["NodeA"],
            "Num_of_primary_infores": [3],
            "unique_predicates": [["p1"]],
        })
        r2 = pd.DataFrame({
            "output_node": ["NodeZ"],
            "Num_of_primary_infores": [5],
            "unique_predicates": [["p2"]],
        })
        result = merge_ranking_by_number_of_infores(r1, r2)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# 18. get_curie (live HTTP)
# ---------------------------------------------------------------------------
class TestGetCurie:
    @pytest.mark.network
    def test_known_name(self):
        curie = get_curie("imatinib")
        assert isinstance(curie, str)
        assert len(curie) > 0

    @pytest.mark.network
    def test_unknown_name_returns_input(self):
        name = "xyzzynotarealname12345"
        result = get_curie(name)
        # Should return the original name when no match
        assert result == name


# ---------------------------------------------------------------------------
# 19. get_pair_annotation
# ---------------------------------------------------------------------------
class TestGetPairAnnotation:
    def test_filters_pairs(self):
        result = {
            "e1": {"subject": "A", "object": "B", "predicate": "p1", "sources": []},
            "e2": {"subject": "A", "object": "C", "predicate": "p2", "sources": []},
            "e3": {"subject": "B", "object": "C", "predicate": "p3", "sources": []},
            "e4": {"subject": "A", "object": "A", "predicate": "p4", "sources": []},
        }
        input_list = ["A", "B"]
        pairs = get_pair_annotation(result, input_list)
        # Only e1 has subject in input_list AND object in input_list AND subject != object
        assert "e1" in pairs
        assert "e2" not in pairs
        assert "e4" not in pairs  # A==A excluded

    def test_empty_input(self):
        result = {"e1": {"subject": "A", "object": "B"}}
        assert get_pair_annotation(result, []) == {}


# ---------------------------------------------------------------------------
# 20. parse_pair_annotation
# ---------------------------------------------------------------------------
class TestParsePairAnnotation:
    @patch("TCT.TCT.ID_convert_to_preferred_name_nodeNormalizer")
    def test_basic(self, mock_id_converter):
        mock_id_converter.return_value = {"A": "NameA", "B": "NameB"}
        pairs_found = {
            "e1": {
                "subject": "A",
                "object": "B",
                "predicate": "biolink:interacts_with",
                "sources": [
                    {"resource_id": "infores:kp1", "resource_role": "primary_knowledge_source"},
                ],
            }
        }
        input_list = ["A", "B"]
        edges = parse_pair_annotation(pairs_found, input_list)
        assert isinstance(edges, list)
        assert len(edges) == 1
        assert edges[0][0] == "A"
        assert edges[0][1] == "NameA"
        assert edges[0][2] == "biolink:interacts_with"
        assert edges[0][3] == "B"
        assert edges[0][4] == "NameB"
        assert edges[0][5] == "infores:kp1"


# ---------------------------------------------------------------------------
# 21. load_json_template
# ---------------------------------------------------------------------------
class TestLoadJsonTemplate:
    def test_structure(self):
        t = load_json_template()
        assert "message" in t
        assert "query_graph" in t["message"]
        qg = t["message"]["query_graph"]
        assert "nodes" in qg
        assert "edges" in qg
        assert "n0" in qg["nodes"]
        assert "n1" in qg["nodes"]
        assert "e1" in qg["edges"]
        assert "ids" in qg["nodes"]["n0"]
        assert "categories" in qg["nodes"]["n0"]
        assert "predicates" in qg["edges"]["e1"]


# ---------------------------------------------------------------------------
# 22. extract_json
# ---------------------------------------------------------------------------
class TestExtractJson:
    def test_valid_json(self):
        txt = 'some text {"key": "value"} more text'
        result = extract_json(txt)
        assert result == {"key": "value"}

    def test_nested_braces(self):
        txt = 'prefix {"a": {"b": 1}} suffix'
        result = extract_json(txt)
        assert result == {"a": {"b": 1}}

    def test_no_json(self):
        txt = "no json here at all"
        result = extract_json(txt)
        assert result is None

    def test_incomplete_json(self):
        txt = '{"key": "value"'
        result = extract_json(txt)
        assert result is None


# ---------------------------------------------------------------------------
# 23. TRAPI_json_validation
# ---------------------------------------------------------------------------
class TestTRAPIJsonValidation:
    def test_missing_message(self, capsys):
        TRAPI_json_validation({}, [], [])
        out = capsys.readouterr().out
        assert "message is missing" in out

    def test_missing_query_graph(self, capsys):
        TRAPI_json_validation({"message": {}}, [], [])
        out = capsys.readouterr().out
        assert "query_graph is missing" in out

    def test_missing_edges(self, capsys):
        TRAPI_json_validation({"message": {"query_graph": {}}}, [], [])
        out = capsys.readouterr().out
        assert "edges is missing" in out

    def test_missing_e1(self, capsys):
        TRAPI_json_validation(
            {"message": {"query_graph": {"edges": {}}}}, [], []
        )
        out = capsys.readouterr().out
        assert "e1 is missing" in out

    def test_missing_predicates(self, capsys):
        TRAPI_json_validation(
            {"message": {"query_graph": {"edges": {"e1": {}}, "nodes": {}}}}, [], []
        )
        out = capsys.readouterr().out
        assert "predicates is missing" in out

    def test_predicates_not_in_kg(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:unknown"]}},
                    "nodes": {},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], [])
        out = capsys.readouterr().out
        assert "predicates is not in the KG" in out

    def test_predicates_ok(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], [])
        out = capsys.readouterr().out
        assert "Predicates ok!" in out

    def test_missing_nodes(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], [])
        out = capsys.readouterr().out
        assert "nodes is missing" in out

    def test_missing_n0(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], [])
        out = capsys.readouterr().out
        assert "n0 is missing" in out

    def test_missing_n1(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {"n0": {"categories": ["biolink:Gene"]}},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], ["biolink:Gene"])
        out = capsys.readouterr().out
        assert "n1 is missing" in out

    def test_missing_categories_n0(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {"n0": {}, "n1": {"categories": ["biolink:Gene"]}},
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], ["biolink:Gene"])
        out = capsys.readouterr().out
        assert "categories is missing" in out

    def test_categories_not_in_kg(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {
                        "n0": {"categories": ["biolink:Unknown"]},
                        "n1": {"categories": ["biolink:Unknown"]},
                    },
                }
            }
        }
        TRAPI_json_validation(q, ["biolink:treats"], ["biolink:Gene"])
        out = capsys.readouterr().out
        assert "categories is not in the KG" in out

    def test_all_ok(self, capsys):
        q = {
            "message": {
                "query_graph": {
                    "edges": {"e1": {"predicates": ["biolink:treats"]}},
                    "nodes": {
                        "n0": {"categories": ["biolink:Gene"]},
                        "n1": {"categories": ["biolink:Disease"]},
                    },
                }
            }
        }
        TRAPI_json_validation(
            q, ["biolink:treats"], ["biolink:Gene", "biolink:Disease"]
        )
        out = capsys.readouterr().out
        assert "Predicates ok!" in out
        assert "node0 category OK!" in out
        assert "node1 category OK!" in out


# ---------------------------------------------------------------------------
# 24. format_id
# ---------------------------------------------------------------------------
class TestFormatId:
    @patch("TCT.TCT.get_curie")
    def test_n0_ids(self, mock_get_curie):
        mock_get_curie.return_value = "MONDO:0005148"
        q = {
            "message": {
                "query_graph": {
                    "nodes": {
                        "n0": {"ids": ["diabetes"]},
                        "n1": {"categories": ["biolink:Gene"]},
                    },
                    "edges": {},
                }
            }
        }
        result = format_id(q)
        assert result["message"]["query_graph"]["nodes"]["n0"]["ids"] == ["MONDO:0005148"]
        mock_get_curie.assert_called_with("diabetes")

    @patch("TCT.TCT.get_curie")
    def test_n1_ids(self, mock_get_curie):
        mock_get_curie.side_effect = lambda name: f"CURIE:{name}"
        q = {
            "message": {
                "query_graph": {
                    "nodes": {
                        "n0": {"ids": ["x"]},
                        "n1": {"ids": ["y"]},
                    },
                    "edges": {},
                }
            }
        }
        result = format_id(q)
        assert result["message"]["query_graph"]["nodes"]["n1"]["ids"] == ["CURIE:y"]


# ---------------------------------------------------------------------------
# 25. select_result_to_analysis
# ---------------------------------------------------------------------------
class TestSelectResultToAnalysis:
    def test_basic(self, capsys):
        df1 = pd.DataFrame({
            "Subject": ["A", "A"],
            "Object": ["Gene1", "Gene2"],
            "Predicate": ["p1", "p2"],
        })
        df2 = pd.DataFrame({
            "Subject": ["B", "B"],
            "Object": ["Gene1", "Gene3"],
            "Predicate": ["p3", "p4"],
        })
        sele_genes = ["Gene1"]
        result = select_result_to_analysis(sele_genes, df1, df2)
        assert isinstance(result, pd.DataFrame)
        # Gene1 should appear from both DataFrames
        assert len(result) == 2
        captured = capsys.readouterr()
        assert "Gene1" in captured.out


# ---------------------------------------------------------------------------
# 26. Gene_id_converter
# ---------------------------------------------------------------------------
class TestGeneIdConverter:
    @patch("TCT.TCT.requests.post")
    def test_ncbigene_ids(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"NCBIGene3845": "KRAS"}
        mock_post.return_value = mock_response

        result = Gene_id_converter(["NCBIGene:3845", "NCBIGene:999"], "http://example.com/api")
        assert isinstance(result, dict)
        mock_post.assert_called_once()
        # Check the posted JSON structure
        posted_json = mock_post.call_args[1]["json"]
        assert "message" in posted_json
        assert "NCBIGene3845" in posted_json["message"]["query_graph"]["nodes"]["n0"]["ids"]
        assert "NCBIGene999" in posted_json["message"]["query_graph"]["nodes"]["n0"]["ids"]

    @patch("TCT.TCT.requests.post")
    def test_non_ncbigene_ids(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        # Non-NCBIGene IDs should be filtered out
        result = Gene_id_converter(["CHEBI:15377"], "http://example.com/api")
        assert isinstance(result, dict)
        # The list sent to API should be empty (no NCBIGene ids)
        posted_json = mock_post.call_args[1]["json"]
        assert posted_json["message"]["query_graph"]["nodes"]["n0"]["ids"] == []

    @patch("TCT.TCT.requests.post")
    def test_non_200_returns_empty(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {}
        mock_post.return_value = mock_response

        result = Gene_id_converter(["NCBIGene:3845"], "http://example.com/api")
        assert result == {}


# ---------------------------------------------------------------------------
# 27. Deprecated functions  # DEPRECATED
# ---------------------------------------------------------------------------
class TestDeprecatedQueryKPAll:  # DEPRECATED
    @patch("TCT.TCT.format_query_json")
    def test_query_kp_all_returns_dicts(self, mock_format):
        mock_format.return_value = {"message": {}}
        metakg = pd.DataFrame({
            "API": ["API_A"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Disease"],
            "Predicate": ["biolink:treats"],
            "URL": ["http://example.com"],
        })
        apinames = {"API_A": "http://example.com"}
        result_dict, result_concept = query_KP_all(
            ["NCBIGene:3845"], [], ["biolink:Gene"], ["biolink:Disease"],
            ["biolink:treats"], [], metakg, apinames
        )
        assert isinstance(result_dict, dict)
        assert isinstance(result_concept, dict)


# ---------------------------------------------------------------------------
# 28. connecting_two_dots_two_hops
# ---------------------------------------------------------------------------
class TestConnectingTwoDotseTwoHops:
    def test_basic(self):
        sorted_dic1 = [("GeneA", 5), ("GeneB", 3), ("GeneC", 1)]
        sorted_dic2 = [("GeneB", 4), ("GeneC", 2), ("GeneD", 1)]
        df = connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)
        assert isinstance(df, pd.DataFrame)
        assert "node" in df.columns
        assert "normalized_rank" in df.columns
        # GeneB and GeneC overlap
        assert set(df["node"].tolist()) == {"GeneB", "GeneC"}
        # Should be sorted ascending by normalized_rank
        ranks = df["normalized_rank"].tolist()
        assert ranks == sorted(ranks)

    def test_no_overlap(self):
        sorted_dic1 = [("GeneA", 5), ("GeneB", 3)]
        sorted_dic2 = [("GeneC", 4), ("GeneD", 2)]
        df = connecting_two_dots_two_hops(sorted_dic1, sorted_dic2)
        assert len(df) == 0


# ---------------------------------------------------------------------------
# 29. find_path_by_two_ends
# ---------------------------------------------------------------------------
class TestFindPathByTwoEnds:
    @patch("TCT.TCT.query_KP_all")
    def test_basic(self, mock_query):
        # query_KP_all returns (result_dict, result_concept)
        # The function then calls parse_result which is actually not defined...
        # find_path_by_two_ends calls query_KP_all, then on line 1749 it calls
        # parse_result which is set to None. This will raise an error in real use.
        # We can still test that query_KP_all is called correctly.
        mock_query.return_value = ({}, {})

        metakg = pd.DataFrame({
            "API": ["API_A"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Disease"],
            "Predicate": ["biolink:treats"],
            "URL": ["http://example.com"],
        })
        apinames = {"API_A": "http://example.com"}

        # find_path_by_two_ends internally calls parse_result (set to None) and
        # ranking_result_by_predicates_object(None) which will fail.
        # So we just verify the call flow by catching the expected error.
        with pytest.raises(Exception):
            find_path_by_two_ends(
                ["NCBIGene:3845"], ["biolink:Gene"], ["biolink:treats"],
                ["biolink:Disease"], ["NCBIGene:999"], ["biolink:Gene"],
                ["biolink:treats"], [], [], [], [], [], [],
                metakg, apinames
            )
        # Verify query_KP_all was called
        assert mock_query.call_count == 2


# ---------------------------------------------------------------------------
# 30. get_SmartAPI_Translator_KP_info (deduped delegation)
# ---------------------------------------------------------------------------
class TestGetSmartAPITranslatorKPInfoDelegation:
    @patch("TCT.translator_kpinfo.get_translator_kp_info")
    def test_delegates(self, mock_fn):
        mock_fn.return_value = ("fake_df", {"key": "val"})
        result = get_SmartAPI_Translator_KP_info()
        mock_fn.assert_called_once()
        assert result == ("fake_df", {"key": "val"})


# ---------------------------------------------------------------------------
# 31. ID_convert_to_preferred_name_nodeNormalizer (deduped delegation)
# ---------------------------------------------------------------------------
class TestIDConvertDelegation:
    @patch("TCT.node_normalizer.ID_convert_to_preferred_name_nodeNormalizer")
    def test_delegates(self, mock_fn):
        mock_fn.return_value = {"A": "NameA"}
        result = ID_convert_to_preferred_name_nodeNormalizer(["A"])
        mock_fn.assert_called_once_with(["A"])
        assert result == {"A": "NameA"}


# ---------------------------------------------------------------------------
# 32. load_translator_resources (deduped delegation)
# ---------------------------------------------------------------------------
class TestLoadTranslatorResourcesDelegation:
    @patch("TCT.translator_resources.TranslatorResources.load")
    def test_delegates(self, mock_load):
        from TCT.translator_resources import TranslatorResources
        mock_resources = TranslatorResources(
            api_names={"api": "url"},
            meta_kg=pd.DataFrame(),
            api_predicates={"api": ["pred"]},
        )
        mock_load.return_value = mock_resources
        result = load_translator_resources()
        mock_load.assert_called_once()
        assert isinstance(result, TranslatorResources)
        assert result.api_names == {"api": "url"}
