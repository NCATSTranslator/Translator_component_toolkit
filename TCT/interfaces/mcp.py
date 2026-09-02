"""Expose the curated Translator Component Toolkit tools through MCP.

This adapter registers the interface-neutral callables from
:mod:`TCT.interfaces.tools` with FastMCP and converts unexpected failures into
protocol-level errors. FastMCP uses its default stdio transport when ``main``
is invoked through the installed ``tct-server`` command.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult
from mcp import types as mcp_types
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, ErrorData

from . import tools as shared_tools
from .invocation import ToolInvocationError, invoke as invoke_tool
from .observability import flush_observability, use_incoming_trace_context


mcp = FastMCP("TCT")


def _metadata_mapping(value: Any) -> dict[str, Any]:
    """Convert protocol metadata to an ordinary mapping, preserving extras."""
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(by_alias=True, exclude_none=True)
    return {}


class _TraceContextMiddleware(Middleware):
    """Restore client trace context without publishing it as a tool argument."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mcp_types.CallToolRequestParams],
        call_next: Any,
    ) -> ToolResult:
        message = context.message
        metadata = _metadata_mapping(message.meta)
        arguments = dict(message.arguments or {})

        # Some agent MCP wrappers currently place protocol metadata alongside
        # tool arguments. Accept that convention without leaking it into the
        # callable contract or failing FastMCP argument validation.
        argument_metadata = _metadata_mapping(arguments.pop("_meta", None))
        metadata = {**argument_metadata, **metadata}
        if arguments != (message.arguments or {}):
            message = message.model_copy(update={"arguments": arguments})
            context = context.copy(message=message)

        with use_incoming_trace_context(metadata):
            return await call_next(context)


mcp.add_middleware(_TraceContextMiddleware())

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
            return invoke_tool(tool, *args, _interface="mcp", **kwargs)
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
        _ERROR_PREFIXES[_tool.__name__],
    )


def main() -> None:
    """Entry point for the installed ``tct-server`` command."""
    try:
        mcp.run()
    finally:
        # The SDK batches events while the long-running server is active.
        flush_observability()


__all__ = ["main", "mcp", *[tool.__name__ for tool in shared_tools.TOOLS]]
