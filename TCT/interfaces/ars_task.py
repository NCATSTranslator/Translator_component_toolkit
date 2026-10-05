"""MCP-only ARS finder flow exposed as a SEP-1686 background task.

This module intentionally avoids ``from __future__ import annotations``:
FastMCP resolves ``Progress`` dependency parameters from real annotations, and
PEP 563 string annotations defeat that resolution.

A blocking ARS query runs 15 s to 15 min. Task-aware clients get a task ID
immediately and poll progress; task-unaware clients degrade to a plain
blocking call (SEP-1686 graceful degradation).
"""

from asyncio import to_thread as asyncio_to_thread
from typing import Any

from fastmcp.dependencies import Progress
from fastmcp.server.tasks import TaskConfig

from .. import Query_ARS as ars
from . import tools as shared_tools


async def query_ars(
    node: list[str],
    neighbor_categories: list[str],
    predicates: list[str] | None = None,
    top_n: int = 20,
    progress: Progress = Progress(),
) -> Any:
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
    status = await asyncio_to_thread(
        ars.wait_for_ARS, pk, poll_interval=15.0, max_retries=60
    )
    await progress.set_message(f"ARS status: {status.status}")
    await progress.increment()
    result = await asyncio_to_thread(ars.get_ARS_result, status)
    await progress.increment()

    payload: dict[str, Any] = {
        "pk": result.pk,
        "merged_pk": result.merged_pk,
        "status": result.status.status,
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


def register(mcp) -> Any:
    """Register ``query_ars`` on the given FastMCP instance and return the tool."""
    return mcp.tool(
        name="query_ars",
        task=TaskConfig(mode="optional"),
        annotations={"readOnlyHint": False, "openWorldHint": True},
    )(query_ars)  # pragma: no cover - registration wrapper
