"""Shared invocation and result serialization for agent-facing interfaces."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import fields, is_dataclass
from enum import Enum
from typing import Any


class ToolInvocationError(RuntimeError):
    """Represent a shared tool failure before an interface translates it."""

    def __init__(self, tool_name: str, cause: Exception) -> None:
        self.tool_name = tool_name
        self.cause = cause
        super().__init__(str(cause))

    @property
    def contextual_message(self) -> str:
        """Return the failure with context derived from the public tool name."""
        tool_label = self.tool_name.replace("_", " ").capitalize()
        return f"{tool_label} error: {self.cause}"


class ResultSerializationError(RuntimeError):
    """Represent a failure to convert a successful result into JSON."""

    def __init__(self, cause: Exception) -> None:
        self.cause = cause
        super().__init__(str(cause))


def invoke(tool: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """Invoke a shared tool and normalize its ordinary failure boundary."""
    try:
        return tool(*args, **kwargs)
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
