"""Regression tests for the installed MCP server entry point."""

import inspect
import pytest


pytest.importorskip("fastmcp")


def test_main_entry_point_exists():
    """Test that main.py has the entry point function."""
    import main

    assert hasattr(main, "main")
    assert callable(main.main)


def test_main_imports_mcp_server():
    """Test that main.py imports the MCP server for orchestrating agent access."""
    import main

    assert hasattr(main, "mcp")
    assert main.mcp is not None


def test_main_module_is_a_compatible_view_of_the_mcp_adapter():
    """The repository launcher delegates to the packaged implementation."""
    import main
    from TCT.interfaces import mcp as adapter

    assert main.main is adapter.main
    assert main.mcp is adapter.mcp


def test_main_function_simple():
    """Test that main() function is simple wrapper."""
    import main

    # Should be a simple function with no parameters
    sig = inspect.signature(main.main)
    assert len(sig.parameters) == 0

    # Should have proper docstring
    assert main.main.__doc__ is not None
    assert "Entry point" in main.main.__doc__


def test_main_runs_mcp_with_default_transport(monkeypatch):
    """The installed command continues to use FastMCP's default transport."""
    import main

    calls = []
    monkeypatch.setattr(
        main.mcp, "run", lambda *args, **kwargs: calls.append((args, kwargs))
    )

    main.main()

    assert calls == [((), {})]

