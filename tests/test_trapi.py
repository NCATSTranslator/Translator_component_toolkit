import json

import pytest
import requests
from unittest.mock import patch, MagicMock

from TCT.trapi import build_query, query


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
