"""Simple tests for TCT MCP Server functionality."""

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
    assert hasattr(mcp, 'run'), "MCP server should be runnable for agents"
    assert mcp.name == "TCT", "MCP server should have correct name for agents"


def test_mcp_tools_accessible():
    """Test that MCP tools are accessible to orchestrating agent."""
    from TCT.server import name_lookup, normalize_nodes
    
    # These should exist as tool objects that agents can call
    assert name_lookup is not None, "name_lookup tool should be accessible"
    assert normalize_nodes is not None, "normalize_nodes tool should be accessible"
