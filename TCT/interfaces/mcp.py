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
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from . import ars_task, tools as shared_tools
from .invocation import ToolInvocationError, invoke as invoke_tool
from .observability import flush_observability, use_incoming_trace_context


mcp = FastMCP("TCT")

# Tools that only read data or produce derived copies; everything else may
# mutate the metadata structures passed in. All tools reach out to network
# services, so openWorldHint is always true.
_READ_ONLY_TOOLS = frozenset(
    {
        "ARS_neighborhood_finder",
        "ARS_pathfinder",
        # submit_ars_query intentionally absent: it creates an ARS submission.
        "get_ars_status",
        "get_ars_results",
        "query_ars",
        "get_translator_resources",
        "name_lookup",
        "get_name_synonyms",
        "batch_name_lookup",
        "normalize_nodes",
        "get_kp_info",
        "get_metakg_data",
        "get_api_predicates",
        "optimize_query_for_api",
        "query_knowledge_provider",
        "parallel_query_apis",
        "trapi_query_endpoint",
        "neighborhood_finder",
        "path_finder",
    }
)


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
        context: MiddlewareContext,
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


def _register_tool(
    tool: Callable[..., Any],
) -> Any:
    """Register one shared callable while preserving its introspected contract."""

    @wraps(tool)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return invoke_tool(tool, *args, _interface="mcp", **kwargs)
        except ToolInvocationError as error:
            # FastMCP converts ToolError into a protocol-level tool error result
            # carrying the contextual message.
            raise ToolError(error.contextual_message) from error

    annotations = {
        "readOnlyHint": tool.__name__ in _READ_ONLY_TOOLS,
        "openWorldHint": True,
    }
    return mcp.tool(annotations=annotations)(invoke)


for _tool in shared_tools.TOOLS:
    globals()[_tool.__name__] = _register_tool(_tool)


# MCP-only background-task surface (see TCT.interfaces.ars_task).
query_ars = ars_task.register(mcp)


def main() -> None:
    """Entry point for the installed ``tct-server`` command."""
    try:
        mcp.run()
    finally:
        # The SDK batches events while the long-running server is active.
        flush_observability()


__all__ = ["main", "mcp", "query_ars", *[tool.__name__ for tool in shared_tools.TOOLS]]
