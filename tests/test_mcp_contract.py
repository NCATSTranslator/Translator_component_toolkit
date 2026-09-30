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
    "validate_query_workflow": "(workflow: 'dict[str, Any]') -> 'dict[str, Any]'",
    "run_query_workflow": "(workflow: 'dict[str, Any]') -> 'dict[str, Any]'",
    "replay_query_workflow": "(bundle: 'dict[str, Any]', mode: 'str' = 'snapshot') -> 'dict[str, Any]'",
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
    """Existing tools keep their outputs; new workflows use structured results."""
    tools = asyncio.run(mcp.get_tools())

    for name, tool in tools.items():
        if name in {
            "validate_query_workflow",
            "run_query_workflow",
            "replay_query_workflow",
        }:
            assert tool.output_schema is not None
        else:
            assert tool.output_schema is None


def test_workflow_tool_inputs_are_explicit_json_objects():
    tools = asyncio.run(mcp.get_tools())
    for name in ("validate_query_workflow", "run_query_workflow"):
        schema = _without_titles(tools[name].parameters)
        assert schema["properties"] == {
            "workflow": {"type": "object", "additionalProperties": True}
        }
        assert schema["required"] == ["workflow"]
    schema = _without_titles(tools["replay_query_workflow"].parameters)
    assert schema["properties"] == {
        "bundle": {"type": "object", "additionalProperties": True},
        "mode": {"type": "string", "default": "snapshot"},
    }
    assert schema["required"] == ["bundle"]


def test_mcp_workflow_returns_structured_replayable_evidence():
    """Exercise the actual registered MCP adapters, including JSON output."""

    async def roundtrip():
        tools = await mcp.get_tools()
        workflow = {
            "schema_version": 1,
            "steps": [{"id": "data", "op": "literal", "value": ["EXAMPLE:1"]}],
            "outputs": {"ids": {"$ref": "data"}},
        }
        result = await tools["run_query_workflow"].run({"workflow": workflow})
        bundle = result.structured_content
        replayed = await tools["replay_query_workflow"].run({"bundle": bundle})
        assert bundle["status"] == "succeeded"
        assert replayed.structured_content["outputs"] == {"ids": ["EXAMPLE:1"]}
        assert replayed.structured_content["replayed_from"] == bundle["bundle_sha256"]

    asyncio.run(roundtrip())
