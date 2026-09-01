"""Shared invocation and result serialization for agent-facing interfaces."""

from __future__ import annotations

import inspect
import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any

from .observability import observe_tool


class ToolInvocationError(RuntimeError):
    """Represent a shared tool failure before an interface translates it."""

    def __init__(self, tool_name: str, cause: Exception) -> None:
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(str(cause))


class ResultSerializationError(RuntimeError):
    """Represent a failure to convert a successful result into JSON."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


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


def invoke(
    tool: Callable[..., Any],
    /,
    *args: Any,
    _interface: str | None = None,
    **kwargs: Any,
) -> Any:
    """Invoke and optionally observe a tool at an interface boundary."""
    try:
        metadata = {
            "tct.interface": _interface or "shared",
            "tct.module": tool.__module__,
            "tct.tool": tool.__name__,
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
            result = tool(*args, **kwargs)
            if observation is not None:
                output = _trace_value(result)
                observation.update(
                    output=output,
                    metadata=_payload_metadata("tct.output", output),
                )
            return result
    except ToolInvocationError:
        raise
    except Exception as error:
        raise ToolInvocationError(tool.__name__, error) from error


def to_jsonable(value: Any) -> Any:
    """Recursively convert common TCT results into JSON-compatible values."""
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Enum):
        return to_jsonable(value.value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(item) for item in sorted(value, key=str)]
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in fields(value)
        }

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return to_jsonable(model_dump(mode="json"))
        except TypeError:
            return to_jsonable(model_dump())

    if value.__class__.__module__.startswith("pandas."):
        if value.__class__.__name__ == "DataFrame":
            return to_jsonable(value.to_dict(orient="records"))
        to_dict = getattr(value, "to_dict", None)
        if callable(to_dict):
            return to_jsonable(to_dict())

    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_jsonable(to_dict())

    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        return to_jsonable(to_list())

    item = getattr(value, "item", None)
    if callable(item):
        try:
            return to_jsonable(item())
        except ValueError:
            pass

    return str(value)


def dumps_result(value: Any) -> str:
    """Serialize a tool result as stable, human-readable JSON."""
    try:
        return json.dumps(to_jsonable(value), indent=2, sort_keys=True)
    except Exception as error:
        raise ResultSerializationError(error) from error


__all__ = [
    "ResultSerializationError",
    "ToolInvocationError",
    "dumps_result",
    "invoke",
    "to_jsonable",
]
