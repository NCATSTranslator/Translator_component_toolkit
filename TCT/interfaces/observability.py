"""Optional observability for agent-facing TCT interfaces.

This module deliberately imports Langfuse only when tracing is enabled. The
core library and its shared tool functions therefore remain independent of
the observability SDK.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from typing import Any


_ENABLED_VARIABLE = "TCT_LANGFUSE_ENABLED"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


class ObservabilityConfigurationError(RuntimeError):
    """Report an invalid or incomplete optional observability setup."""


def langfuse_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether Langfuse tracing is enabled for interface invocations.

    ``TCT_LANGFUSE_ENABLED`` takes precedence when set. Otherwise, tracing is
    enabled automatically when both standard Langfuse API keys are present.
    """
    variables = os.environ if environ is None else environ
    configured = variables.get(_ENABLED_VARIABLE)
    if configured is not None:
        normalized = configured.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
        raise ObservabilityConfigurationError(
            f"{_ENABLED_VARIABLE} must be one of: "
            "1, true, yes, on, 0, false, no, off"
        )
    return bool(
        variables.get("LANGFUSE_PUBLIC_KEY")
        and variables.get("LANGFUSE_SECRET_KEY")
    )


def _get_langfuse_client() -> Any | None:
    if not langfuse_enabled():
        return None
    try:
        langfuse = importlib.import_module("langfuse")
    except ModuleNotFoundError as error:
        if error.name != "langfuse":
            raise
        raise ObservabilityConfigurationError(
            "Langfuse tracing is enabled but its SDK is not installed; "
            "install TCT with the 'langfuse' extra"
        ) from error
    return langfuse.get_client()


@contextmanager
def observe_tool(
    *,
    name: str,
    input_factory: Callable[[], Any],
    metadata: Mapping[str, Any],
) -> Generator[Any | None, None, None]:
    """Open a Langfuse tool observation, or yield ``None`` when disabled."""
    client = _get_langfuse_client()
    if client is None:
        yield None
        return

    with client.start_as_current_observation(
        as_type="tool",
        name=name,
        input=input_factory(),
        metadata=dict(metadata),
    ) as observation:
        yield observation


def flush_observability() -> None:
    """Flush enabled tracing without importing Langfuse in untraced runs."""
    try:
        client = _get_langfuse_client()
    except ObservabilityConfigurationError:
        # Invocation reports setup errors with the relevant tool context. A
        # cleanup attempt must not replace that useful interface error.
        return
    if client is not None:
        client.flush()


__all__ = [
    "ObservabilityConfigurationError",
    "flush_observability",
    "langfuse_enabled",
    "observe_tool",
]
