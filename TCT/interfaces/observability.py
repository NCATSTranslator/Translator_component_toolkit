"""Optional observability for agent-facing TCT interfaces.

This module deliberately imports Langfuse only when tracing is enabled. The
core library and its shared tool functions therefore remain independent of
the observability SDK.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any


logger = logging.getLogger(__name__)


def _warn(operation: str, error: Exception) -> None:
    """Report telemetry failures without logging credentials or payloads."""
    if isinstance(error, ObservabilityConfigurationError):
        # These messages are authored here and contain no configuration values.
        logger.warning("Unable to %s: %s", operation, error)
    else:
        logger.warning("Unable to %s (%s)", operation, type(error).__name__)


_ENABLED_VARIABLE = "TCT_LANGFUSE_ENABLED"
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_TRACE_CONTEXT_FIELDS = frozenset({"traceparent", "tracestate", "baggage"})
_PROPAGATED_TRACE_CONTEXT: ContextVar[bool] = ContextVar(
    "tct_propagated_trace_context",
    default=False,
)


class ObservabilityConfigurationError(RuntimeError):
    """Report an invalid or incomplete optional observability setup."""


def langfuse_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether Langfuse tracing is enabled for interface invocations.

    Tracing is disabled by default and requires ``TCT_LANGFUSE_ENABLED`` to be
    set to an accepted true value. Langfuse credentials alone never activate
    instrumentation.
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
            f"{_ENABLED_VARIABLE} must be one of: 1, true, yes, on, 0, false, no, off"
        )
    return False


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
def use_incoming_trace_context(
    metadata: Mapping[str, Any] | None,
) -> Generator[None, None, None]:
    """Restore W3C trace context supplied by an MCP client when tracing.

    Imports remain lazy so MCP and core installations do not acquire a hard
    OpenTelemetry dependency. Unknown MCP metadata is deliberately ignored.
    """
    carrier = {
        key: value
        for key, value in (metadata or {}).items()
        if key in _TRACE_CONTEXT_FIELDS and isinstance(value, str)
    }
    if not carrier:
        yield
        return

    try:
        enabled = langfuse_enabled()
        if enabled:
            otel_context = importlib.import_module("opentelemetry.context")
            otel_propagate = importlib.import_module("opentelemetry.propagate")
            extracted = otel_propagate.extract(carrier)
            otel_token = otel_context.attach(extracted)
    except Exception as error:
        _warn("restore trace context", error)
        yield
        return
    if not enabled:
        yield
        return
    propagated_token = _PROPAGATED_TRACE_CONTEXT.set(True)
    try:
        yield
    finally:
        _PROPAGATED_TRACE_CONTEXT.reset(propagated_token)
        try:
            otel_context.detach(otel_token)
        except Exception as error:
            _warn("detach trace context", error)


def trace_context_was_propagated() -> bool:
    """Return whether the current invocation inherited client trace context."""
    return _PROPAGATED_TRACE_CONTEXT.get()


@contextmanager
def observe_tool(
    *,
    name: str,
    input_factory: Callable[[], Any],
    metadata: Mapping[str, Any],
) -> Generator[Any | None, None, None]:
    """Observe a tool without letting SDK failures alter its outcome."""
    try:
        client = _get_langfuse_client()
        if client is not None:
            context = client.start_as_current_observation(
                as_type="tool",
                name=name,
                input=input_factory(),
                metadata=dict(metadata),
            )
            observation = context.__enter__()
    except Exception as error:
        _warn("start tool observation", error)
        yield None
        return
    if client is None:
        yield None
        return
    try:
        yield observation
    except BaseException:
        # Notify the SDK of the original tool failure, but never let it
        # suppress or replace that exception (including cancellation).
        try:
            context.__exit__(*sys.exc_info())
        except Exception as error:
            _warn("finish failed tool observation", error)
        raise
    else:
        try:
            context.__exit__(None, None, None)
        except Exception as error:
            _warn("finish tool observation", error)


def flush_observability() -> None:
    """Flush enabled tracing without importing Langfuse in untraced runs."""
    try:
        client = _get_langfuse_client()
        if client is not None:
            client.flush()
    except Exception as error:
        _warn("flush tool observations", error)


__all__ = [
    "ObservabilityConfigurationError",
    "flush_observability",
    "langfuse_enabled",
    "observe_tool",
    "trace_context_was_propagated",
    "use_incoming_trace_context",
]
