"""Expose the curated Translator Component Toolkit tools through MCP.

The interface-neutral tool callables live in :mod:`TCT.interfaces.tools`.
This module owns FastMCP registration and converts unexpected failures into
the protocol-level errors returned by the existing ``tct-server`` command.

``TCT.server`` remains the compatibility import path for the MCP server and
its registered tool objects. FastMCP uses its default stdio transport when the
server is run through ``tct-server`` or ``python main.py``.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, ErrorData

from .interfaces import tools as shared_tools


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
}


def _register_tool(
    tool: Callable[..., Any],
    error_prefix: str,
) -> Any:
    """Register one shared callable while preserving its introspected contract."""

    @wraps(tool)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return tool(*args, **kwargs)
        except Exception as error:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=f"{error_prefix}: {str(error)}",
                )
            ) from error

    return mcp.tool()(invoke)


for _tool in shared_tools.TOOLS:
    globals()[_tool.__name__] = _register_tool(
        _tool,
        _ERROR_PREFIXES[_tool.__name__],
    )


__all__ = ["mcp", *[tool.__name__ for tool in shared_tools.TOOLS]]
