"""Tests for the interface-neutral shared tool surface."""

import inspect
import subprocess
import sys
from pathlib import Path

from TCT.interfaces import tools


EXPECTED_TOOL_NAMES = [
    "get_translator_resources",
    "name_lookup",
    "get_name_synonyms",
    "batch_name_lookup",
    "normalize_nodes",
    "get_kp_info",
    "get_metakg_data",
    "add_custom_api_to_metakg",
    "add_plover_apis_to_metakg",
    "get_api_predicates",
    "optimize_query_for_api",
    "query_knowledge_provider",
    "parallel_query_apis",
    "trapi_query_endpoint",
    "neighborhood_finder",
    "path_finder",
]


def test_registry_is_an_explicit_ordered_collection_of_plain_functions():
    """Only the curated ordinary callables are exposed to adapters."""
    assert [tool.__name__ for tool in tools.TOOLS] == EXPECTED_TOOL_NAMES
    assert all(inspect.isfunction(tool) for tool in tools.TOOLS)
    assert all(inspect.getdoc(tool) for tool in tools.TOOLS)
    assert all(
        inspect.signature(tool).return_annotation is not inspect.Signature.empty
        for tool in tools.TOOLS
    )


def test_shared_tools_import_without_mcp_dependencies():
    """CLI and Python consumers do not need the optional MCP extra."""
    project_root = Path(__file__).parents[1]
    script = """
import sys

class RejectMcpImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp" or fullname.startswith(("mcp.", "fastmcp")):
            raise AssertionError(f"unexpected MCP import: {fullname}")
        return None

sys.meta_path.insert(0, RejectMcpImports())
from TCT.interfaces.cli import build_parser
from TCT.interfaces.tools import TOOLS
assert len(TOOLS) == 16
assert build_parser().prog == "tct"
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_shared_tool_delegates_without_protocol_wrapping(monkeypatch):
    """The shared layer returns library values directly."""
    calls = []

    def fake_lookup(query, return_top_response, return_synonyms):
        calls.append((query, return_top_response, return_synonyms))
        return {"resolved": query}

    monkeypatch.setattr(tools, "lookup", fake_lookup)

    result = tools.name_lookup(
        "aspirin",
        return_top_response=False,
        return_synonyms=True,
    )

    assert result == {"resolved": "aspirin"}
    assert calls == [("aspirin", False, True)]
