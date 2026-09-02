"""Expose the curated Translator Component Toolkit tools through MCP.

This adapter registers the interface-neutral callables from
:mod:`TCT.interfaces.tools` with FastMCP and converts unexpected failures into
protocol-level errors. FastMCP uses its default stdio transport when ``main``
is invoked through the installed ``tct-server`` command.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, ErrorData

from . import tools as shared_tools
from .invocation import ToolInvocationError, invoke as invoke_tool


mcp = FastMCP("TCT")

_ERROR_PREFIXES = {
    "get_translator_resources": "Get translator resources error",
    "name_lookup": "Name lookup error",
    "get_name_synonyms": "Synonyms lookup error",
    "batch_name_lookup": "Batch lookup error",
    "normalize_nodes": "Node normalization error",
    "get_kp_info": "KP info error",
    "get_metakg_data": "MetaKG data error",
    "add_custom_api_to_metakg": "Add custom API error",
    "add_plover_apis_to_metakg": "Add Plover APIs error",
    "get_api_predicates": "API predicates error",
    "optimize_query_for_api": "Query optimization error",
    "query_knowledge_provider": "KP query error",
    "parallel_query_apis": "Parallel query error",
    "trapi_query_endpoint": "TRAPI query error",
    "neighborhood_finder": "Neighborhood finder error",
    "path_finder": "Path finder error",
    "submit_ars_query": "ARS submit error",
    "get_ars_status": "ARS status error",
    "wait_for_ars_results": "ARS wait error",
    "get_ars_results": "ARS results error",
    "query_ars": "ARS query error",
    "ars_neighborhood_finder": "ARS neighborhood finder error",
}


def _register_tool(
    tool: Callable[..., Any],
    error_prefix: str,
) -> Any:
    """Register one shared callable while preserving its introspected contract."""

    @wraps(tool)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return invoke_tool(tool, *args, **kwargs)
        except ToolInvocationError as error:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"{error_prefix}: {str(error.cause)}",
                )
            ) from error

    return mcp.tool()(invoke)


for _tool in shared_tools.TOOLS:
    globals()[_tool.__name__] = _register_tool(
        _tool,
        _ERROR_PREFIXES.get(_tool.__name__, f"{_tool.__name__} error"),
    )


def main() -> None:
    """Entry point for the installed ``tct-server`` command."""
    mcp.run()


__all__ = ["main", "mcp", *[tool.__name__ for tool in shared_tools.TOOLS]]
