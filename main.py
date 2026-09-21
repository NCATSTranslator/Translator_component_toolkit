"""Compatibility launcher for running the TCT MCP server from the repository."""

from TCT.interfaces.mcp import main, mcp

__all__ = ["main", "mcp"]

if __name__ == "__main__":
    main()
