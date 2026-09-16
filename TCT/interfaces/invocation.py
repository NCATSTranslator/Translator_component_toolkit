"""Shared invocation and result serialization for agent-facing interfaces."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .serialization import ResultSerializationError, dumps_result, to_jsonable
from .telemetry import observe_invocation


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


def invoke(
    tool: Callable[..., Any],
    /,
    *args: Any,
    _interface: str | None = None,
    **kwargs: Any,
) -> Any:
    """Run a tool once and translate its exception for the calling interface."""
    try:
        with observe_invocation(tool, args, kwargs, _interface) as record_result:
            result = tool(*args, **kwargs)
            record_result(result)
            return result
    except ToolInvocationError:
        raise
    except Exception as error:
        raise ToolInvocationError(tool.__name__, error) from error


__all__ = [
    "ResultSerializationError",
    "ToolInvocationError",
    "dumps_result",
    "invoke",
    "to_jsonable",
]
