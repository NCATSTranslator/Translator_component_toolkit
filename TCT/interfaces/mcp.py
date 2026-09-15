"""Expose the curated Translator Component Toolkit tools through MCP.

This adapter registers the interface-neutral callables from
:mod:`TCT.interfaces.tools` with FastMCP and converts unexpected failures into
protocol-level errors. FastMCP uses its default stdio transport when ``main``
is invoked through the installed ``tct-server`` command.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from fastmcp import FastMCP
from mcp.shared.exceptions import McpError
from mcp.types import INTERNAL_ERROR, ErrorData

from . import tools as shared_tools
from .invocation import ToolInvocationError, invoke as invoke_tool


mcp = FastMCP("TCT")


def _register_tool(
    tool: Callable[..., Any],
) -> Any:
    """Register one shared callable while preserving its introspected contract."""

    @wraps(tool)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        try:
            return invoke_tool(tool, *args, **kwargs)
        except ToolInvocationError as error:
            raise McpError(
                ErrorData(
                    code=INTERNAL_ERROR,
                    message=error.contextual_message,
                )
            ) from error

    return mcp.tool()(invoke)


for _tool in shared_tools.TOOLS:
    globals()[_tool.__name__] = _register_tool(_tool)


def main() -> None:
    """Entry point for the installed ``tct-server`` command."""
    mcp.run()


__all__ = ["main", "mcp", *[tool.__name__ for tool in shared_tools.TOOLS]]
