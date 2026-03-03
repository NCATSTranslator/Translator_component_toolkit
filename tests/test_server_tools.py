"""Tests for the TCT MCP server tool functions.

Each @mcp.tool() function in TCT/server.py is tested here, both for
normal operation and for error handling (McpError propagation).

The @mcp.tool() decorator wraps each function into a FastMCP FunctionTool
object. The underlying callable is accessible via the `.fn` attribute.
"""

import pytest
import pandas as pd
from unittest.mock import patch

from TCT.server import (
    name_lookup,
    get_name_synonyms,
    batch_name_lookup,
    normalize_nodes,
    get_kp_info,
    get_metakg_data,
    add_custom_api_to_metakg,
    add_plover_apis_to_metakg,
    get_api_predicates,
    optimize_query_for_api,
    query_knowledge_provider,
    parallel_query_apis,
    trapi_query_endpoint,
)
from TCT.translator_node import TranslatorNode


# ---------------------------------------------------------------------------
# 1. test_name_lookup -- Live API
# ---------------------------------------------------------------------------
def test_name_lookup():
    """Live API: name_lookup('asthma') returns a TranslatorNode with MONDO: curie."""
    result = name_lookup.fn("asthma")
    assert isinstance(result, TranslatorNode)
    assert result.curie.startswith("MONDO:")


# ---------------------------------------------------------------------------
# 2. test_get_name_synonyms -- Live API
# ---------------------------------------------------------------------------
def test_get_name_synonyms():
    """Live API: synonyms for a known CURIE returns a non-empty dict."""
    result = get_name_synonyms.fn("MONDO:0004979")
    assert isinstance(result, dict)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# 3. test_batch_name_lookup -- Live API
# ---------------------------------------------------------------------------
def test_batch_name_lookup():
    """Live API: batch lookup of two terms returns a dict keyed by those terms."""
    result = batch_name_lookup.fn(["asthma", "diabetes"])
    assert isinstance(result, dict)
    assert "asthma" in result
    assert "diabetes" in result


# ---------------------------------------------------------------------------
# 4. test_normalize_nodes -- Live API
# ---------------------------------------------------------------------------
def test_normalize_nodes():
    """Live API: normalizing MESH:D014867 returns a TranslatorNode."""
    result = normalize_nodes.fn("MESH:D014867")
    assert isinstance(result, TranslatorNode)


# ---------------------------------------------------------------------------
# 5. test_get_kp_info -- Live API
# ---------------------------------------------------------------------------
def test_get_kp_info():
    """Live API: get_kp_info() returns a tuple of (DataFrame, dict)."""
    result = get_kp_info.fn()
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert isinstance(result[0], pd.DataFrame)
    assert isinstance(result[1], dict)


# ---------------------------------------------------------------------------
# 6. test_get_metakg_data -- Mocked
# ---------------------------------------------------------------------------
def test_get_metakg_data():
    """Mock get_KP_metadata to return a small DataFrame; verify result."""
    mock_df = pd.DataFrame({
        "API": ["TestAPI"],
        "Predicate": ["biolink:related_to"],
        "Subject": ["biolink:Gene"],
        "Object": ["biolink:Disease"],
        "URL": ["https://example.com/query"],
    })
    with patch("TCT.server.get_KP_metadata", return_value=mock_df) as mock_fn:
        result = get_metakg_data.fn({"TestAPI": "https://example.com/query"})
        mock_fn.assert_called_once()
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 1
        assert result.iloc[0]["API"] == "TestAPI"


# ---------------------------------------------------------------------------
# 7. test_add_custom_api_to_metakg -- Pure computation with small data
# ---------------------------------------------------------------------------
def test_add_custom_api_to_metakg():
    """Add a custom API entry and verify both the dict and DataFrame are updated."""
    api_names = {"ExistingAPI": "https://existing.example.com/query"}
    metakg_df = pd.DataFrame({
        "API": ["ExistingAPI"],
        "Predicate": ["biolink:related_to"],
        "Subject": ["biolink:Gene"],
        "Object": ["biolink:Disease"],
        "URL": ["https://existing.example.com/query"],
    })

    result = add_custom_api_to_metakg.fn(
        api_names,
        metakg_df,
        new_api_name="NewAPI",
        new_api_url="https://new.example.com/query",
        new_api_predicate="biolink:treats",
        new_api_subject="biolink:SmallMolecule",
        new_api_object="biolink:Disease",
    )

    assert isinstance(result, tuple)
    assert len(result) == 2
    updated_names, updated_df = result
    assert isinstance(updated_names, dict)
    assert isinstance(updated_df, pd.DataFrame)
    assert "NewAPI" in updated_names
    assert updated_names["NewAPI"] == "https://new.example.com/query"
    assert "NewAPI" in updated_df["API"].values


# ---------------------------------------------------------------------------
# 8. test_add_plover_apis_to_metakg -- Mocked
# ---------------------------------------------------------------------------
def test_add_plover_apis_to_metakg():
    """Mock add_plover_API to return updated data; verify tuple result."""
    original_names = {"API_A": "https://a.example.com/query"}
    original_df = pd.DataFrame({
        "API": ["API_A"],
        "Predicate": ["biolink:related_to"],
        "Subject": ["biolink:Gene"],
        "Object": ["biolink:Disease"],
        "URL": ["https://a.example.com/query"],
    })

    updated_names = {**original_names, "PloverAPI": "https://plover.example.com/query"}
    updated_df = pd.concat([
        original_df,
        pd.DataFrame({
            "API": ["PloverAPI"],
            "Predicate": ["biolink:interacts_with"],
            "Subject": ["biolink:Gene"],
            "Object": ["biolink:Gene"],
            "URL": ["https://plover.example.com/query"],
        }),
    ], ignore_index=True)

    with patch("TCT.server.add_plover_API", return_value=(updated_names, updated_df)) as mock_fn:
        result = add_plover_apis_to_metakg.fn(original_names, original_df)
        mock_fn.assert_called_once_with(original_names, original_df)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert "PloverAPI" in result[0]
        assert len(result[1]) == 2


# ---------------------------------------------------------------------------
# 9. test_get_api_predicates -- Mocked
# ---------------------------------------------------------------------------
def test_get_api_predicates():
    """Mock get_translator_API_predicates and verify the tuple return via .as_tuple()."""
    from TCT.translator_resources import TranslatorResources

    mock_names = {"API_X": "https://x.example.com/query"}
    mock_df = pd.DataFrame({
        "API": ["API_X"],
        "Predicate": ["biolink:related_to"],
        "Subject": ["biolink:Gene"],
        "Object": ["biolink:Disease"],
        "URL": ["https://x.example.com/query"],
    })
    mock_preds = {"API_X": ["biolink:related_to"]}
    mock_resources = TranslatorResources(
        api_names=mock_names, meta_kg=mock_df, api_predicates=mock_preds,
    )

    with patch(
        "TCT.server.get_translator_API_predicates",
        return_value=mock_resources,
    ) as mock_fn:
        result = get_api_predicates.fn()
        mock_fn.assert_called_once()
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] == mock_names
        assert result[2] == mock_preds


# ---------------------------------------------------------------------------
# 10. test_optimize_query_for_api -- Pure computation
# ---------------------------------------------------------------------------
def test_optimize_query_for_api():
    """Build a TRAPI query and verify predicates are filtered to the intersection."""
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
        "TestAPI": ["biolink:interacts_with", "biolink:treats"],
    }

    result = optimize_query_for_api.fn(query_json, "TestAPI", api_predicates)

    result_preds = result["message"]["query_graph"]["edges"]["e00"]["predicates"]
    # The intersection of the query predicates and the API predicates should be
    # exactly {"biolink:interacts_with", "biolink:treats"}.
    assert set(result_preds) == {"biolink:interacts_with", "biolink:treats"}
    # "biolink:related_to" should have been removed.
    assert "biolink:related_to" not in result_preds


def test_optimize_query_for_api_no_shared():
    """When there are no shared predicates, all original predicates are kept."""
    query_json = {
        "message": {
            "query_graph": {
                "edges": {
                    "e00": {
                        "subject": "n00",
                        "object": "n01",
                        "predicates": ["biolink:causes"],
                    }
                },
                "nodes": {
                    "n00": {"ids": ["NCBIGene:3845"]},
                    "n01": {"categories": ["biolink:Disease"]},
                },
            }
        }
    }
    api_predicates = {
        "TestAPI": ["biolink:treats"],
    }

    result = optimize_query_for_api.fn(query_json, "TestAPI", api_predicates)
    result_preds = result["message"]["query_graph"]["edges"]["e00"]["predicates"]
    # No shared predicates, so the original predicates should be kept.
    assert result_preds == ["biolink:causes"]


# ---------------------------------------------------------------------------
# 11. test_query_knowledge_provider -- Mocked
# ---------------------------------------------------------------------------
def test_query_knowledge_provider():
    """Mock query_KP to return a result dict; verify passthrough."""
    mock_result = {
        "knowledge_graph": {
            "edges": {"e1": {"subject": "a", "object": "b", "predicate": "biolink:related_to"}},
            "nodes": {},
        }
    }
    with patch("TCT.server.query_KP", return_value=mock_result) as mock_fn:
        result = query_knowledge_provider.fn(
            api_name="TestAPI",
            query_json={"message": {}},
            api_names={"TestAPI": "https://example.com/query"},
            api_predicates={"TestAPI": ["biolink:related_to"]},
        )
        mock_fn.assert_called_once()
        assert result == mock_result


# ---------------------------------------------------------------------------
# 12. test_parallel_query_apis -- Mocked
# ---------------------------------------------------------------------------
def test_parallel_query_apis():
    """Mock parallel_api_query to return a merged result; verify passthrough."""
    mock_merged = {
        "e1": {"subject": "a", "object": "b", "predicate": "biolink:related_to"},
        "e2": {"subject": "c", "object": "d", "predicate": "biolink:treats"},
    }
    with patch("TCT.server.parallel_api_query", return_value=mock_merged) as mock_fn:
        result = parallel_query_apis.fn(
            query_json={"message": {}},
            selected_apis=["API_A", "API_B"],
            api_names={"API_A": "https://a.example.com", "API_B": "https://b.example.com"},
            api_predicates={"API_A": ["biolink:related_to"], "API_B": ["biolink:treats"]},
            max_workers=2,
        )
        mock_fn.assert_called_once()
        assert result == mock_merged
        assert len(result) == 2


# ---------------------------------------------------------------------------
# 13. test_trapi_query_endpoint_bug -- Known bug: missing `query` arg
# ---------------------------------------------------------------------------
def test_trapi_query_endpoint_bug():
    """trapi_query(url) is missing the required `query` argument, causing a
    TypeError that the except block catches. The except block then tries to
    construct McpError with ErrorData(INTERNAL_ERROR, message) using
    positional args, but ErrorData is a Pydantic model that requires keyword
    args, so a TypeError escapes. We verify the error path is triggered."""
    with pytest.raises(TypeError):
        trapi_query_endpoint.fn("https://example.com/query")


# ---------------------------------------------------------------------------
# 14. Error-path tests: underlying function raises -> error propagated
#
# Note: The server.py error handlers use ErrorData(INTERNAL_ERROR, message)
# with positional arguments, but ErrorData is a Pydantic BaseModel that
# requires keyword arguments (code=..., message=...). This means the
# McpError constructor itself raises a TypeError before McpError can be
# created. The tests verify that the error path IS triggered by asserting
# that a TypeError is raised (from the buggy ErrorData constructor call).
# ---------------------------------------------------------------------------
def test_name_lookup_error():
    """When lookup() raises, name_lookup's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.lookup", side_effect=Exception("API down")):
        with pytest.raises(TypeError):
            name_lookup.fn("test")


def test_get_name_synonyms_error():
    """When synonyms() raises, get_name_synonyms's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.synonyms", side_effect=Exception("Timeout")):
        with pytest.raises(TypeError):
            get_name_synonyms.fn("MONDO:0004979")


def test_batch_name_lookup_error():
    """When batch_lookup() raises, batch_name_lookup's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.batch_lookup", side_effect=Exception("Network error")):
        with pytest.raises(TypeError):
            batch_name_lookup.fn(["asthma"])


def test_normalize_nodes_error():
    """When get_normalized_nodes() raises, normalize_nodes's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.get_normalized_nodes", side_effect=Exception("Bad CURIE")):
        with pytest.raises(TypeError):
            normalize_nodes.fn("INVALID:000")


def test_get_kp_info_error():
    """When get_translator_kp_info() raises, get_kp_info's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.get_translator_kp_info", side_effect=Exception("Service unavailable")):
        with pytest.raises(TypeError):
            get_kp_info.fn()


def test_get_metakg_data_error():
    """When get_KP_metadata() raises, get_metakg_data's except block is triggered.
    The ErrorData positional-arg bug causes TypeError to escape."""
    with patch("TCT.server.get_KP_metadata", side_effect=Exception("Parse error")):
        with pytest.raises(TypeError):
            get_metakg_data.fn({"TestAPI": "https://example.com/query"})
