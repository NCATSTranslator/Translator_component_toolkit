"""Derive TCT telemetry without coupling tool execution to a tracing backend."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from typing import Any

from .observability import observe_tool, trace_context_was_propagated
from .serialization import to_jsonable


logger = logging.getLogger(__name__)


def _trace_value(value: Any) -> Any:
    """Prepare trace data without letting conversion break a tool call."""
    try:
        return to_jsonable(value)
    except Exception as error:
        return {"serialization_error": str(error), "value": repr(value)}


def _trace_input(
    tool: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    bound = inspect.signature(tool).bind(*args, **kwargs)
    bound.apply_defaults()
    return _trace_value(dict(bound.arguments))


def _canonical_payload(value: Any) -> bytes:
    """Encode normalized trace data deterministically for size and identity."""
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _payload_metadata(prefix: str, value: Any) -> dict[str, Any]:
    """Describe payload cost and identity without depending on its contents."""
    payload = _canonical_payload(value)
    metadata: dict[str, Any] = {
        f"{prefix}.bytes": len(payload),
        f"{prefix}.sha256": hashlib.sha256(payload).hexdigest(),
        f"{prefix}.type": type(value).__name__,
    }
    if isinstance(value, Mapping):
        metadata[f"{prefix}.item_count"] = len(value)
    elif isinstance(value, list):
        metadata[f"{prefix}.item_count"] = len(value)
    return metadata


def _trapi_query_metadata(query: Any) -> dict[str, Any]:
    """Return small batching indicators from a TRAPI query, when present."""
    if not isinstance(query, Mapping):
        return {}
    message = query.get("message")
    if not isinstance(message, Mapping):
        return {}
    query_graph = message.get("query_graph")
    if not isinstance(query_graph, Mapping):
        return {}
    nodes = query_graph.get("nodes")
    if not isinstance(nodes, Mapping):
        return {}

    identifier_count = 0
    identifier_nodes = 0
    for node in nodes.values():
        if not isinstance(node, Mapping):
            continue
        identifiers = node.get("ids")
        if isinstance(identifiers, list):
            identifier_count += len(identifiers)
            identifier_nodes += 1

    return {
        "tct.query.node_count": len(nodes),
        "tct.query.identifier_count": identifier_count,
        "tct.query.identifier_node_count": identifier_nodes,
    }


def _input_metadata(value: Any) -> dict[str, Any]:
    """Build generic and TCT-specific input metrics for opportunity analysis."""
    metadata = _payload_metadata("tct.input", value)
    if not isinstance(value, Mapping):
        return metadata

    for name, argument in value.items():
        metadata.update(_payload_metadata(f"tct.input.argument.{name}", argument))

    api_name = value.get("api_name")
    if isinstance(api_name, str):
        metadata["tct.provider.name"] = api_name

    selected_apis = value.get("selected_apis")
    if isinstance(selected_apis, list):
        metadata["tct.provider.count"] = len(selected_apis)

    for candidate in ("strings", "node"):
        items = value.get(candidate)
        if isinstance(items, list):
            metadata["tct.batch.item_count"] = len(items)
            metadata["tct.batch.argument"] = candidate
            break

    query = value.get("query")
    if isinstance(query, list):
        metadata["tct.batch.item_count"] = len(query)
        metadata["tct.batch.argument"] = "query"

    metadata.update(_trapi_query_metadata(value.get("query_json")))
    return metadata


@contextmanager
def observe_invocation(
    tool: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    interface: str | None,
) -> Generator[Callable[[Any], None], None, None]:
    """Measure an invocation; recording failures never replace tool outcomes."""
    metadata = {
        "tct.interface": interface or "shared",
        "tct.module": tool.__module__,
        "tct.tool": tool.__name__,
        "tct.trace.propagated": trace_context_was_propagated(),
    }

    def trace_input() -> Any:
        value = _trace_input(tool, args, kwargs)
        metadata.update(_input_metadata(value))
        return value

    with observe_tool(
        name=f"tct.tool.{tool.__name__}",
        input_factory=trace_input,
        metadata=metadata,
    ) as observation:
        def record_result(result: Any) -> None:
            if observation is None:
                return
            try:
                output = _trace_value(result)
                observation.update(
                    output=output,
                    metadata=_payload_metadata("tct.output", output),
                )
            except Exception as error:
                logger.warning("Unable to record tool telemetry (%s)", type(error).__name__)

        yield record_result
