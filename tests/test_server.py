"""Simple tests for TCT MCP Server functionality."""

import asyncio

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
