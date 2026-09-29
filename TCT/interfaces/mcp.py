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

from . import tools as shared_tools
from .invocation import ToolInvocationError, invoke as invoke_tool
from .observability import flush_observability, use_incoming_trace_context


mcp = FastMCP("TCT")

# Tools that only read data or produce derived copies; everything else may
# mutate the metadata structures passed in. All tools reach out to network
# services, so openWorldHint is always true.
_READ_ONLY_TOOLS = frozenset(
    {
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

def _register_ars_task_tool() -> None:
    """Expose the ARS finder flow as a SEP-1686 background task.

    A blocking ARS query runs 15 s to 15 min. Task-aware clients get a task ID
    immediately and poll progress; task-unaware clients degrade to a plain
    blocking call (SEP-1686 graceful degradation).
    """
    import asyncio

    from fastmcp.dependencies import Progress
    from fastmcp.server.tasks import TaskConfig

    from .. import Query_ARS as ars

    async def query_ars(
        node: list[str],
        neighbor_categories: list[str],
        predicates: list[str] | None = None,
        top_n: int = 20,
        progress: Progress = Progress(),
    ) -> dict[str, Any]:
        """Query the Translator ARS end to end and return ranked answer rows.

        Submits a one-hop query, waits for every ARA and the ARS merge agent,
        and returns the top answers. Long-running: expect ~15 s to several
        minutes. Task-aware MCP clients receive a task ID immediately and can
        poll progress instead of waiting; task-unaware clients block until done
        and should raise their call timeout accordingly. Prefer the faster
        submit_ars_query / get_ars_status / get_ars_results workflow otherwise.

        Args:
            node: One or more input nodes, as names ("asthma") or CURIEs
                ("MONDO:0004979"). Names are resolved to CURIEs first.
            neighbor_categories: Biolink categories wanted for neighbors, with
                or without the "biolink:" prefix (for example ["Drug"]).
            predicates: Optional edge predicates to require. Omit for any
                predicate; defaults to biolink:related_to.
            top_n: Number of ranked rows to return (default 20); pass 0 only to
                export the full merged TRAPI message, which can be tens of MB.

        Returns:
            The pk, merged pk, final status, resolved input nodes, and either
            ranked summary rows or the full merged TRAPI message.
        """
        resolved = shared_tools._resolve_nodes(node)
        query = ars.format_query_json_forARS_neighborhood(
            subject_ids=[resolved_node.curie for resolved_node in resolved],
            object_categories=shared_tools._normalize_categories(neighbor_categories),
            predicates=predicates,
        )
        pk = ars.submit_ARS(query)

        await progress.set_total(2)
        await progress.set_message("submitted; waiting for ARA answers")
        status = await asyncio.to_thread(
            ars.wait_for_ARS, pk, poll_interval=15.0, max_retries=60
        )
        await progress.set_message(f"ARS status: {status.status}")
        await progress.increment()
        result = await asyncio.to_thread(ars.get_ARS_result, status)
        await progress.increment()

        payload: dict[str, Any] = {
            "pk": result.pk,
            "merged_pk": result.merged_pk,
            "status": result.status,
            "resolved_nodes": {
                f"node_{index}": resolved_node
                for index, resolved_node in enumerate(resolved)
            },
            "result_count": len(result.results),
        }
        if top_n <= 0:
            payload["message"] = result.raw
        else:
            payload["results"] = result.summarize(top_n)
        return payload

    mcp.tool(
        name="query_ars",
        task=TaskConfig(mode="optional"),
        annotations={"readOnlyHint": True, "openWorldHint": True},
    )(query_ars)
    globals()["query_ars"] = query_ars


_register_ars_task_tool()


def main() -> None:
    """Entry point for the installed ``tct-server`` command."""
    try:
        mcp.run()
    finally:
        # The SDK batches events while the long-running server is active.
        flush_observability()


__all__ = ["main", "mcp", "query_ars", *[tool.__name__ for tool in shared_tools.TOOLS]]
