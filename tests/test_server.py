"""Simple tests for TCT MCP Server functionality."""

import asyncio
from contextlib import contextmanager

import pytest

# Skip this module entirely when the optional MCP extra (fastmcp) is not installed.
pytest.importorskip("fastmcp")

from TCT.server import mcp


def test_mcp_server_exists():
    """Test that MCP server instance exists and has correct name."""
    assert mcp is not None
    assert mcp.name == "TCT"


def test_mcp_server_ready():
    """Test that MCP server is ready for orchestrating agent access."""
    # Check that the server has the FastMCP functionality needed for agents
    assert hasattr(mcp, "run"), "MCP server should be runnable for agents"
    assert mcp.name == "TCT", "MCP server should have correct name for agents"


def test_mcp_tools_accessible():
    """Test that MCP tools are accessible to orchestrating agent."""
    from TCT.server import name_lookup, normalize_nodes

    # These should exist as tool objects that agents can call
    assert name_lookup is not None, "name_lookup tool should be accessible"
    assert normalize_nodes is not None, "normalize_nodes tool should be accessible"


def test_server_module_is_a_compatible_view_of_the_mcp_adapter():
    """Legacy imports resolve to the authoritative adapter objects."""
    from TCT import server
    from TCT.interfaces import mcp as adapter

    assert server.mcp is adapter.mcp
    assert server.name_lookup is adapter.name_lookup
    assert server.path_finder is adapter.path_finder


def test_mcp_adapter_preserves_protocol_error_conversion(monkeypatch):
    """Failures from shared tools remain MCP internal errors for clients."""
    from mcp.shared.exceptions import McpError
    from mcp.types import INTERNAL_ERROR

    from TCT.interfaces import tools
    from TCT.server import name_lookup

    def fail_lookup(*args, **kwargs):
        raise ValueError("lookup failed")

    monkeypatch.setattr(tools, "lookup", fail_lookup)

    with pytest.raises(McpError) as error:
        asyncio.run(name_lookup.run({"query": "aspirin"}))

    assert error.value.error.code == INTERNAL_ERROR
    assert error.value.error.message == "Name lookup error: lookup failed"


def test_mcp_adapter_uses_shared_invocation_boundary(monkeypatch):
    """Successful MCP calls pass through the common agent-facing seam."""
    from TCT.interfaces import mcp as adapter
    from TCT.interfaces import tools

    calls = []

    def fake_invoke(tool, *args, **kwargs):
        calls.append((tool, args, kwargs))
        return {"resolved": kwargs["query"]}

    monkeypatch.setattr(adapter, "invoke_tool", fake_invoke)

    asyncio.run(adapter.name_lookup.run({"query": "aspirin"}))

    assert calls == [
        (
            tools.name_lookup,
            (),
            {
                "query": "aspirin",
                "return_top_response": True,
                "return_synonyms": False,
                "_interface": "mcp",
            },
        )
    ]


def test_mcp_middleware_restores_protocol_context_without_schema_arguments(
    monkeypatch,
):
    """Trace metadata surrounds dispatch and never reaches the shared tool."""
    from fastmcp.server.middleware import MiddlewareContext
    from mcp.types import CallToolRequestParams

    from TCT.interfaces import mcp as adapter

    calls = []

    @contextmanager
    def fake_trace_context(metadata):
        calls.append(("enter", metadata))
        try:
            yield
        finally:
            calls.append(("exit", metadata))

    async def call_next(context):
        calls.append(("arguments", context.message.arguments))
        return "result"

    monkeypatch.setattr(adapter, "use_incoming_trace_context", fake_trace_context)
    params = CallToolRequestParams(
        name="name_lookup",
        arguments={
            "query": "aspirin",
            "_meta": {
                "traceparent": (
                    "00-0123456789abcdef0123456789abcdef-"
                    "0123456789abcdef-01"
                )
            },
        },
        _meta={"baggage": "session.id=conversation-123"},
    )

    result = asyncio.run(
        adapter._TraceContextMiddleware().on_call_tool(
            MiddlewareContext(message=params),
            call_next,
        )
    )

    assert result == "result"
    assert calls == [
        (
            "enter",
            {
                "traceparent": (
                    "00-0123456789abcdef0123456789abcdef-"
                    "0123456789abcdef-01"
                ),
                "baggage": "session.id=conversation-123",
            },
        ),
        ("arguments", {"query": "aspirin"}),
        (
            "exit",
            {
                "traceparent": (
                    "00-0123456789abcdef0123456789abcdef-"
                    "0123456789abcdef-01"
                ),
                "baggage": "session.id=conversation-123",
            },
        ),
    ]
