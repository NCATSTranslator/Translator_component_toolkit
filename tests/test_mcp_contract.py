"""Regression tests for the public TCT MCP discovery contract."""

import asyncio
import inspect

import pytest


pytest.importorskip("fastmcp")

from TCT.interfaces.mcp import mcp


EXPECTED_SIGNATURES = {
    "get_translator_resources": "() -> 'Any'",
    "name_lookup": (
        "(query: 'str', return_top_response: 'bool' = True, "
        "return_synonyms: 'bool' = False) -> 'Any'"
    ),
    "get_name_synonyms": "(query: 'str') -> 'Any'",
    "batch_name_lookup": (
        "(strings: 'list[str]', size: 'int' = 25, "
        "return_top_response: 'bool' = True, "
        "return_synonyms: 'bool' = False) -> 'Any'"
    ),
    "normalize_nodes": (
        "(query: 'str | list[str]', return_equivalent_identifiers: 'bool' = False, "
        "conflate: 'bool' = True, drug_chemical_conflate: 'bool' = False) -> 'Any'"
    ),
    "get_kp_info": "() -> 'Any'",
    "get_metakg_data": "(api_names: 'dict[str, str]') -> 'Any'",
    "add_custom_api_to_metakg": (
        "(api_names: 'dict[str, str]', metakg_df: 'Any', new_api_name: 'str', "
        "new_api_url: 'str', new_api_predicate: 'str', new_api_subject: 'str', "
        "new_api_object: 'str') -> 'Any'"
    ),
    "add_plover_apis_to_metakg": (
        "(api_names: 'dict[str, str]', metakg_df: 'Any') -> 'Any'"
    ),
    "get_api_predicates": "() -> 'Any'",
    "optimize_query_for_api": (
        "(query_json: 'dict[str, Any]', api_name: 'str', "
        "api_predicates: 'dict[str, list[str]]') -> 'Any'"
    ),
    "query_knowledge_provider": (
        "(api_name: 'str', query_json: 'dict[str, Any]', "
        "api_names: 'dict[str, str]', "
        "api_predicates: 'dict[str, list[str]]') -> 'Any'"
    ),
    "parallel_query_apis": (
        "(query_json: 'dict[str, Any]', selected_apis: 'list[str]', "
        "api_names: 'dict[str, str]', api_predicates: 'dict[str, list[str]]', "
        "max_workers: 'int' = 1) -> 'Any'"
    ),
    "trapi_query_endpoint": "(url: 'str') -> 'Any'",
    "neighborhood_finder": (
        "(node: 'list[str]', neighbor_categories: 'list[str]') -> 'Any'"
    ),
    "path_finder": (
        "(start: 'str', end: 'str', "
        "intermediate_categories: 'list[str] | None' = None) -> 'Any'"
    ),
    "submit_ars_query": "(query_json: 'dict[str, Any]') -> 'Any'",
    "get_ars_status": "(pk: 'str') -> 'Any'",
    "wait_for_ars_results": (
        "(pk: 'str', poll_interval: 'float' = 10.0, timeout: 'float' = 900.0) -> 'Any'"
    ),
    "get_ars_results": "(pk: 'str', top_n: 'int' = 20) -> 'Any'",
    "query_ars": (
        "(query_json: 'dict[str, Any]', poll_interval: 'float' = 10.0, "
        "timeout: 'float' = 900.0, top_n: 'int' = 20) -> 'Any'"
    ),
    "ars_neighborhood_finder": (
        "(node: 'list[str]', neighbor_categories: 'list[str]', "
        "predicates: 'list[str] | None' = None, poll_interval: 'float' = 10.0, "
        "timeout: 'float' = 900.0, top_n: 'int' = 20) -> 'Any'"
    ),
}


EXPECTED_INPUTS = {
    "get_translator_resources": ({}, []),
    "name_lookup": (
        {
            "query": {"type": "string"},
            "return_top_response": {"default": True, "type": "boolean"},
            "return_synonyms": {"default": False, "type": "boolean"},
        },
        ["query"],
    ),
    "get_name_synonyms": ({"query": {"type": "string"}}, ["query"]),
    "batch_name_lookup": (
        {
            "strings": {"items": {"type": "string"}, "type": "array"},
            "size": {"default": 25, "type": "integer"},
            "return_top_response": {"default": True, "type": "boolean"},
            "return_synonyms": {"default": False, "type": "boolean"},
        },
        ["strings"],
    ),
    "normalize_nodes": (
        {
            "query": {
                "anyOf": [
                    {"type": "string"},
                    {"items": {"type": "string"}, "type": "array"},
                ]
            },
            "return_equivalent_identifiers": {
                "default": False,
                "type": "boolean",
            },
            "conflate": {"default": True, "type": "boolean"},
            "drug_chemical_conflate": {"default": False, "type": "boolean"},
        },
        ["query"],
    ),
    "get_kp_info": ({}, []),
    "get_metakg_data": (
        {
            "api_names": {
                "additionalProperties": {"type": "string"},
                "type": "object",
            }
        },
        ["api_names"],
    ),
    "add_custom_api_to_metakg": (
        {
            "api_names": {
                "additionalProperties": {"type": "string"},
                "type": "object",
            },
            "metakg_df": {},
            "new_api_name": {"type": "string"},
            "new_api_url": {"type": "string"},
            "new_api_predicate": {"type": "string"},
            "new_api_subject": {"type": "string"},
            "new_api_object": {"type": "string"},
        },
        [
            "api_names",
            "metakg_df",
            "new_api_name",
            "new_api_url",
            "new_api_predicate",
            "new_api_subject",
            "new_api_object",
        ],
    ),
    "add_plover_apis_to_metakg": (
        {
            "api_names": {
                "additionalProperties": {"type": "string"},
                "type": "object",
            },
            "metakg_df": {},
        },
        ["api_names", "metakg_df"],
    ),
    "get_api_predicates": ({}, []),
    "optimize_query_for_api": (
        {
            "query_json": {"additionalProperties": True, "type": "object"},
            "api_name": {"type": "string"},
            "api_predicates": {
                "additionalProperties": {
                    "items": {"type": "string"},
                    "type": "array",
                },
                "type": "object",
            },
        },
        ["query_json", "api_name", "api_predicates"],
    ),
    "query_knowledge_provider": (
        {
            "api_name": {"type": "string"},
            "query_json": {"additionalProperties": True, "type": "object"},
            "api_names": {
                "additionalProperties": {"type": "string"},
                "type": "object",
            },
            "api_predicates": {
                "additionalProperties": {
                    "items": {"type": "string"},
                    "type": "array",
                },
                "type": "object",
            },
        },
        ["api_name", "query_json", "api_names", "api_predicates"],
    ),
    "parallel_query_apis": (
        {
            "query_json": {"additionalProperties": True, "type": "object"},
            "selected_apis": {
                "items": {"type": "string"},
                "type": "array",
            },
            "api_names": {
                "additionalProperties": {"type": "string"},
                "type": "object",
            },
            "api_predicates": {
                "additionalProperties": {
                    "items": {"type": "string"},
                    "type": "array",
                },
                "type": "object",
            },
            "max_workers": {"default": 1, "type": "integer"},
        },
        ["query_json", "selected_apis", "api_names", "api_predicates"],
    ),
    "trapi_query_endpoint": ({"url": {"type": "string"}}, ["url"]),
    "neighborhood_finder": (
        {
            "node": {"items": {"type": "string"}, "type": "array"},
            "neighbor_categories": {
                "items": {"type": "string"},
                "type": "array",
            },
        },
        ["node", "neighbor_categories"],
    ),
    "path_finder": (
        {
            "start": {"type": "string"},
            "end": {"type": "string"},
            "intermediate_categories": {
                "anyOf": [
                    {"items": {"type": "string"}, "type": "array"},
                    {"type": "null"},
                ],
                "default": None,
            },
        },
        ["start", "end"],
    ),
    "submit_ars_query": (
        {"query_json": {"additionalProperties": True, "type": "object"}},
        ["query_json"],
    ),
    "get_ars_status": ({"pk": {"type": "string"}}, ["pk"]),
    "wait_for_ars_results": (
        {
            "pk": {"type": "string"},
            "poll_interval": {"default": 10.0, "type": "number"},
            "timeout": {"default": 900.0, "type": "number"},
        },
        ["pk"],
    ),
    "get_ars_results": (
        {"pk": {"type": "string"}, "top_n": {"default": 20, "type": "integer"}},
        ["pk"],
    ),
    "query_ars": (
        {
            "query_json": {"additionalProperties": True, "type": "object"},
            "poll_interval": {"default": 10.0, "type": "number"},
            "timeout": {"default": 900.0, "type": "number"},
            "top_n": {"default": 20, "type": "integer"},
        },
        ["query_json"],
    ),
    "ars_neighborhood_finder": (
        {
            "node": {"items": {"type": "string"}, "type": "array"},
            "neighbor_categories": {"items": {"type": "string"}, "type": "array"},
            "predicates": {
                "anyOf": [
                    {"items": {"type": "string"}, "type": "array"},
                    {"type": "null"},
                ],
                "default": None,
            },
            "poll_interval": {"default": 10.0, "type": "number"},
            "timeout": {"default": 900.0, "type": "number"},
            "top_n": {"default": 20, "type": "integer"},
        },
        ["node", "neighbor_categories"],
    ),
}


def _without_titles(value):
    if isinstance(value, dict):
        return {
            key: _without_titles(item) for key, item in value.items() if key != "title"
        }
    if isinstance(value, list):
        return [_without_titles(item) for item in value]
    return value


def test_published_tool_names_signatures_and_docs_are_stable():
    """The curated tools retain their names, Python contracts, and descriptions."""
    tools = asyncio.run(mcp.get_tools())

    assert list(tools) == list(EXPECTED_SIGNATURES)
    for name, expected_signature in EXPECTED_SIGNATURES.items():
        tool = tools[name]
        assert str(inspect.signature(tool.fn)) == expected_signature
        assert tool.description == inspect.getdoc(tool.fn)
        assert tool.description


def test_generated_mcp_input_schemas_are_stable():
    """Type annotations and defaults continue to produce compatible schemas."""
    tools = asyncio.run(mcp.get_tools())

    for name, (properties, required) in EXPECTED_INPUTS.items():
        schema = _without_titles(tools[name].parameters)
        assert schema["type"] == "object"
        assert schema["properties"] == properties
        assert schema.get("required", []) == required


def test_tools_keep_unstructured_output_contract():
    """Adding annotations must not silently enable structured MCP outputs."""
    tools = asyncio.run(mcp.get_tools())

    assert all(tool.output_schema is None for tool in tools.values())
