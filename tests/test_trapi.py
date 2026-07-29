import json
import inspect

import pytest
import requests
from unittest.mock import patch, MagicMock

from TCT.trapi import build_query, query, HopSpec, build_multi_hop_query, _build_node_spec


# ---------------------------------------------------------------------------
# build_query tests
# ---------------------------------------------------------------------------

class TestBuildQuery:
    """Tests for the build_query function."""

    def test_return_json_true(self):
        """With return_json=True, returns a JSON string."""
        result = build_query(
            subject_ids=["NCBIGene:3845"],
            object_categories=["biolink:Gene"],
            predicates=["biolink:physically_interacts_with"],
            return_json=True,
        )

        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "message" in parsed
        assert "query_graph" in parsed["message"]
        edges = parsed["message"]["query_graph"]["edges"]
        assert "e00" in edges
        assert edges["e00"]["predicates"] == ["biolink:physically_interacts_with"]
        nodes = parsed["message"]["query_graph"]["nodes"]
        assert nodes["n00"]["ids"] == ["NCBIGene:3845"]
        assert nodes["n01"]["categories"] == ["biolink:Gene"]

    def test_return_json_false(self):
        """With return_json=False, returns a dict."""
        result = build_query(
            subject_ids=["NCBIGene:3845"],
            object_categories=["biolink:Gene"],
            predicates=["biolink:physically_interacts_with"],
            return_json=False,
        )

        assert isinstance(result, dict)
        assert "message" in result
        edges = result["message"]["query_graph"]["edges"]
        assert edges["e00"]["subject"] == "n00"
        assert edges["e00"]["object"] == "n01"

    def test_with_object_ids_parameter(self):
        """Passing object_ids does not raise an error (parameter accepted)."""
        result = build_query(
            subject_ids=["NCBIGene:3845"],
            object_categories=["biolink:Gene"],
            predicates=["biolink:interacts_with"],
            return_json=False,
            object_ids=["CHEBI:15377"],
        )

        assert isinstance(result, dict)
        assert "message" in result

    def test_multiple_predicates(self):
        """Multiple predicates are preserved in the query."""
        predicates = [
            "biolink:physically_interacts_with",
            "biolink:positively_correlated_with",
        ]
        result = build_query(
            subject_ids=["NCBIGene:3845"],
            object_categories=["biolink:Gene"],
            predicates=predicates,
            return_json=False,
        )

        result_predicates = result["message"]["query_graph"]["edges"]["e00"]["predicates"]
        assert result_predicates == predicates


# ---------------------------------------------------------------------------
# query tests
# ---------------------------------------------------------------------------

class TestQuery:
    """Tests for the query function with mocked HTTP calls."""

    @patch("TCT.trapi.requests.post")
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

        result = query("https://example.com/query", {"message": {}})

        assert result is not None
        assert "knowledge_graph" in result
        assert "e1" in result["knowledge_graph"]["edges"]

    @patch("TCT.trapi.requests.post")
    def test_200_with_empty_edges_returns_none(self, mock_post):
        """200 response with knowledge_graph but empty edges returns None."""
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

        result = query("https://example.com/query", {"message": {}})
        assert result is None

    @patch("TCT.trapi.requests.post")
    def test_non_200_raises_request_exception(self, mock_post):
        """Non-200 response raises requests.RequestException."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(requests.RequestException):
            query("https://example.com/query", {"message": {}})


# ---------------------------------------------------------------------------
# _build_node_spec tests
# ---------------------------------------------------------------------------


class TestBuildNodeSpec:
    def test_ids_only(self):
        result = _build_node_spec(ids=["CURIE:1"])
        assert result == {"ids": ["CURIE:1"]}

    def test_categories_only(self):
        result = _build_node_spec(categories=["biolink:Gene"])
        assert result == {"categories": ["biolink:Gene"]}

    def test_both(self):
        result = _build_node_spec(ids=["CURIE:1"], categories=["biolink:Gene"])
        assert result == {"ids": ["CURIE:1"], "categories": ["biolink:Gene"]}

    def test_neither(self):
        result = _build_node_spec()
        assert result == {}


# ---------------------------------------------------------------------------
# build_multi_hop_query tests
# ---------------------------------------------------------------------------


class TestBuildMultiHopQuery:
    def test_single_hop_structure(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(predicates=["biolink:interacts_with"], object_categories=["biolink:Gene"])],
            return_json=False,
        )
        qg = result["message"]["query_graph"]
        assert "n00" in qg["nodes"]
        assert "n01" in qg["nodes"]
        assert "e00" in qg["edges"]
        assert qg["edges"]["e00"]["subject"] == "n00"
        assert qg["edges"]["e00"]["object"] == "n01"

    def test_single_hop_equivalent_to_build_query(self):
        multi = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(predicates=["biolink:interacts_with"], object_categories=["biolink:Gene"])],
            return_json=False,
        )
        single = build_query(
            subject_ids=["NCBIGene:3845"],
            object_categories=["biolink:Gene"],
            predicates=["biolink:interacts_with"],
            return_json=False,
        )
        # Both should produce equivalent query graphs
        multi_qg = multi["message"]["query_graph"]
        single_qg = single["message"]["query_graph"]
        assert multi_qg["edges"]["e00"]["subject"] == single_qg["edges"]["e00"]["subject"]
        assert multi_qg["edges"]["e00"]["object"] == single_qg["edges"]["e00"]["object"]
        assert multi_qg["edges"]["e00"]["predicates"] == single_qg["edges"]["e00"]["predicates"]
        assert multi_qg["nodes"]["n00"]["ids"] == single_qg["nodes"]["n00"]["ids"]
        assert multi_qg["nodes"]["n01"]["categories"] == single_qg["nodes"]["n01"]["categories"]

    def test_two_hop_gene_intermediate_disease(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            subject_categories=["biolink:Gene"],
            hops=[
                HopSpec(predicates=["biolink:related_to"], object_categories=["biolink:BiologicalProcess"]),
                HopSpec(predicates=["biolink:related_to"], object_ids=["MONDO:0005148"]),
            ],
            return_json=False,
        )
        qg = result["message"]["query_graph"]
        assert len(qg["nodes"]) == 3
        assert len(qg["edges"]) == 2
        assert qg["nodes"]["n00"]["ids"] == ["NCBIGene:3845"]
        assert qg["nodes"]["n01"]["categories"] == ["biolink:BiologicalProcess"]
        assert qg["nodes"]["n02"]["ids"] == ["MONDO:0005148"]

    def test_three_hop_chain(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[
                HopSpec(object_categories=["biolink:Gene"]),
                HopSpec(object_categories=["biolink:Disease"]),
                HopSpec(object_categories=["biolink:Drug"]),
            ],
            return_json=False,
        )
        qg = result["message"]["query_graph"]
        assert len(qg["nodes"]) == 4
        assert len(qg["edges"]) == 3

    def test_return_json_true(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(object_categories=["biolink:Gene"])],
            return_json=True,
        )
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "message" in parsed

    def test_return_json_false(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(object_categories=["biolink:Gene"])],
            return_json=False,
        )
        assert isinstance(result, dict)

    def test_omits_none_ids(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(object_categories=["biolink:Gene"])],
            return_json=False,
        )
        assert "ids" not in result["message"]["query_graph"]["nodes"]["n01"]

    def test_omits_none_categories(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(object_ids=["CHEBI:15377"])],
            return_json=False,
        )
        assert "categories" not in result["message"]["query_graph"]["nodes"]["n01"]

    def test_predicates_none_omitted(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[HopSpec(object_categories=["biolink:Gene"])],
            return_json=False,
        )
        assert "predicates" not in result["message"]["query_graph"]["edges"]["e00"]

    def test_validates_empty_hops(self):
        with pytest.raises(ValueError, match="At least one HopSpec"):
            build_multi_hop_query(subject_ids=["NCBIGene:3845"], hops=[])

    def test_validates_no_subject(self):
        with pytest.raises(ValueError, match="subject_ids.*subject_categories"):
            build_multi_hop_query(hops=[HopSpec(object_categories=["biolink:Gene"])])

    def test_node_wiring_is_sequential(self):
        result = build_multi_hop_query(
            subject_ids=["NCBIGene:3845"],
            hops=[
                HopSpec(object_categories=["biolink:Gene"]),
                HopSpec(object_categories=["biolink:Disease"]),
            ],
            return_json=False,
        )
        edges = result["message"]["query_graph"]["edges"]
        assert edges["e00"]["subject"] == "n00"
        assert edges["e00"]["object"] == "n01"
        assert edges["e01"]["subject"] == "n01"
        assert edges["e01"]["object"] == "n02"


# ---------------------------------------------------------------------------
# predicate_query branch tests (merged from upstream):
# build_query defaults to returning a dict (return_json=False);
# query() accepts a dict instead of a JSON string.
# ---------------------------------------------------------------------------

# Test data
EXAMPLE_QUERIES = [
    {
        'subject_ids': ['NCBIGene:3845'],
        'object_categories': ['biolink:Gene'],
        'predicates': ['biolink:physically_interacts_with'],
    },
    {
        'subject_ids': ['NCBIGene:3845'],
        'object_categories': ['biolink:Gene'],
        'predicates': [
            'biolink:positively_correlated_with',
            'biolink:physically_interacts_with',
        ],
    },
]


def test_build_query_returns_dict_by_default():
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'])
    assert isinstance(result, dict)


def test_build_query_default_is_explicitly_false():
    sig = inspect.signature(build_query)
    assert sig.parameters['return_json'].default is False


def test_build_query_returns_json_string_when_requested():
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=True)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_build_query_dict_and_json_are_equivalent():
    q = EXAMPLE_QUERIES[0]
    dict_result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=False)
    json_result = build_query(q['subject_ids'], q['object_categories'], q['predicates'], return_json=True)
    assert dict_result == json.loads(json_result)


@pytest.mark.parametrize("example_query", EXAMPLE_QUERIES)
def test_build_query_structure(example_query):
    result = build_query(
        example_query['subject_ids'],
        example_query['object_categories'],
        example_query['predicates'],
    )
    assert 'message' in result
    qg = result['message']['query_graph']
    assert qg['edges']['e00']['predicates'] == example_query['predicates']
    assert qg['edges']['e00']['subject'] == 'n00'
    assert qg['edges']['e00']['object'] == 'n01'
    assert qg['nodes']['n00']['ids'] == example_query['subject_ids']
    assert qg['nodes']['n01']['categories'] == example_query['object_categories']


def test_query_signature_expects_dict():
    sig = inspect.signature(query)
    assert sig.parameters['query'].annotation is dict


def test_build_query_output_matches_query_input_type():
    """build_query's default output type should match what query() expects."""
    q = EXAMPLE_QUERIES[0]
    result = build_query(q['subject_ids'], q['object_categories'], q['predicates'])
    sig = inspect.signature(query)
    assert isinstance(result, sig.parameters['query'].annotation)
