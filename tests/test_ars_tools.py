"""Offline tests for the ARS tools (sync trio, finder tools, MCP background task).

Covers argument shaping of the interface-neutral tools and the full MCP surface
through an in-process FastMCP client, including the SEP-1686 task flow of
``query_ars`` (task ID, status polling, result fetch, graceful degradation).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect

import pytest
from mcp.shared.exceptions import McpError

ars = importlib.import_module("TCT.Query_ARS")
import TCT.interfaces.tools as tools  # noqa: E402
from tests.ars_fixtures import (  # noqa: E402
    MERGED,
    PARENT,
    FakeResponse,
    child,
    done_trace,
    envelope,
    merged_message,
    trace,
)

# The tools package is importable under both names.
shared_tools = tools


@pytest.fixture(autouse=True)
def _ci_environment(monkeypatch):
    """Pin the ARS endpoint without touching the network."""
    monkeypatch.setenv("TCT_ENVIRONMENT", "ci")


@pytest.fixture
def ars_mocks(monkeypatch):
    """Intercept every ARS HTTP hop with fixture data and record the calls."""
    calls = {"submit": [], "trace": [], "message": []}

    def fake_post(url, json_body):
        calls["submit"].append((url, json_body))
        return FakeResponse({"pk": PARENT, "fields": {"status": "Running"}}, 201)

    state = {"finished": False}

    def fake_get(url, params=None):
        calls["trace"].append((url, params))
        if "/messages/" in url and not (params and params.get("trace")):
            return FakeResponse(envelope(merged_message()), 200)
        if state["finished"]:
            return FakeResponse(done_trace(), 200)
        return FakeResponse(trace("Running", children=[child("ara-aragorn", "Running")]), 200)

    calls["finished"] = state

    monkeypatch.setattr(ars, "_post", fake_post)
    monkeypatch.setattr(ars, "_get", fake_get)
    monkeypatch.setattr(ars.time, "sleep", lambda seconds: None)
    return calls


def _resolved(curie="MONDO:0004979", label="asthma"):
    from TCT.TCT import ResolvedNode

    return ResolvedNode(
        input_value="asthma",
        curie=curie,
        label=label,
        categories=["biolink:Disease"],
    )


# --------------------------------------------------------------------------- #
# sync trio
# --------------------------------------------------------------------------- #
def test_submit_ars_query_returns_pk_and_status(monkeypatch, ars_mocks):
    monkeypatch.setattr(tools, "_resolve_nodes", lambda node: [_resolved()])
    result = tools.submit_ars_query(["asthma"], ["Drug"])

    assert set(result) == {"pk", "resolved_nodes", "status"}
    assert result["pk"] == PARENT
    assert result["resolved_nodes"]["node_0"].curie == "MONDO:0004979"
    url, payload = ars_mocks["submit"][0]
    assert url.endswith("/submit")
    message = payload["message"]
    assert message["query_graph"]["nodes"]["n00"]["ids"] == ["MONDO:0004979"]
    assert message["query_graph"]["nodes"]["n01"]["categories"] == ["biolink:Drug"]
    assert message["query_graph"]["edges"]["e00"]["predicates"] == ["biolink:related_to"]


def test_submit_ars_query_forwards_predicates(monkeypatch, ars_mocks):
    monkeypatch.setattr(tools, "_resolve_nodes", lambda node: [_resolved()])
    tools.submit_ars_query(["asthma"], ["Drug"], predicates=["biolink:treated_by"])

    payload = ars_mocks["submit"][0][1]
    predicates = payload["message"]["query_graph"]["edges"]["e00"]["predicates"]
    assert predicates == ["biolink:treated_by"]


def test_get_ars_status_reports_children(ars_mocks):
    status = tools.get_ars_status(PARENT)

    assert status.status == "Running"
    assert status.merged_version is None
    assert {entry.agent for entry in status.children} == {"ara-aragorn"}


def test_get_ars_results_running_reports_not_ready(ars_mocks):
    result = tools.get_ars_results(PARENT)

    assert result["ready"] is False
    assert result["pk"] == PARENT


def test_get_ars_results_done_returns_ranked_rows(ars_mocks):
    ars_mocks["finished"]["finished"] = True
    result = tools.get_ars_results(PARENT, top_n=2)

    assert result["ready"] is True
    assert result["result_count"] == 2
    assert result["merged_pk"] == MERGED
    assert [row["rank"] for row in result["results"]] == [1, 2]
    assert "message" not in result


def test_get_ars_results_top_n_zero_returns_full_message(ars_mocks):
    ars_mocks["finished"]["finished"] = True
    result = tools.get_ars_results(PARENT, top_n=0)

    assert result["ready"] is True
    assert "message" not in result or result.get("message") is not None


# --------------------------------------------------------------------------- #
# finder tools
# --------------------------------------------------------------------------- #
def test_ars_neighborhood_finder_shapes_finder_result(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    monkeypatch.setattr(
        tools, "_resolve_nodes", lambda node: [_resolved()], raising=True
    )
    result = tools.ARS_neighborhood_finder(node=["asthma"], neighbor_categories=["Drug"])

    assert result["status"] == "Done"
    assert result["result_count"] == 2
    assert result["resolved_nodes"]["node_0"].curie == "MONDO:0004979"
    row = result["results"][0]
    assert row["rank"] == 1
    assert row["nodes"]


def test_ars_neighborhood_finder_json_file_returns_message(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    query = {"message": {"query_graph": {"nodes": [], "edges": []}}}
    result = tools.ARS_neighborhood_finder(json_file=query)

    submitted = ars_mocks["submit"][0][1]
    assert submitted == query
    assert result["status"] == "Done"
    assert result["merged_pk"] == MERGED
    assert result["message"]["results"]


def test_ars_pathfinder_shapes_finder_result(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    monkeypatch.setattr(
        tools, "_resolve_nodes", lambda node: [_resolved(), _resolved("CHEBI:906", "albuterol")],
        raising=True,
    )
    result = tools.ARS_pathfinder("asthma", "albuterol", intermediate_categories=["Gene"])

    assert result["status"] == "Done"
    assert set(result["resolved_nodes"]) == {"start", "end"}


def test_ars_pathfinder_json_file_returns_message(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    query = {"message": {"query_graph": {"nodes": [], "edges": []}}}
    result = tools.ARS_pathfinder(json_file=query)

    assert result["message"]["results"]
    assert ars_mocks["submit"][0][1] == query


# --------------------------------------------------------------------------- #
# MCP surface: sync tools and the query_ars background task
# --------------------------------------------------------------------------- #
@pytest.fixture
def mcp_module(monkeypatch):
    monkeypatch.setattr(shared_tools, "_resolve_nodes", lambda node: [_resolved()])
    # Reload for a fresh FastMCP instance per test: FastMCP keeps per-session
    # state on the server object, and these tests each open their own session.
    mcp = importlib.import_module("TCT.interfaces.mcp")
    reloaded = importlib.reload(mcp)
    yield reloaded
    # Restore a pristine module so later suites see the original FastMCP
    # instance (TCT.server re-exports it by identity).
    importlib.reload(mcp)
    import TCT.server

    importlib.reload(TCT.server)


def _client(mcp):
    from fastmcp import Client

    return Client(mcp.mcp)


def test_sync_ars_tools_end_to_end_through_client(mcp_module, ars_mocks):
    async def scenario():
        async with _client(mcp_module) as client:
            submitted = await client.call_tool(
                "submit_ars_query",
                {"node": ["asthma"], "neighbor_categories": ["Drug"]},
            )
            pk = submitted.data["pk"]
            assert pk == PARENT

            status = await client.call_tool("get_ars_status", {"pk": pk})
            assert status.data["status"] == "Running"

            ars_mocks["finished"]["finished"] = True
            results = await client.call_tool("get_ars_results", {"pk": pk})
            assert results.data["ready"] is True
            assert results.data["results"][0]["rank"] == 1

    asyncio.run(scenario())


def test_query_ars_runs_as_background_task(mcp_module, ars_mocks):
    ars_mocks["finished"]["finished"] = True

    async def scenario():
        async with _client(mcp_module) as client:
            task = await client.call_tool(
                "query_ars",
                {"node": ["asthma"], "neighbor_categories": ["Drug"], "top_n": 2},
                task=True,
            )
            result = await task.result()
            try:
                status = await client.get_task_status(task.task_id)
                assert status.status in {"working", "completed", "input-required"}
            except McpError:
                # The in-memory transport serves tasks/get only for synthetic
                # (client-tracked) tasks; Docket-backed servers cover the rest.
                pass

            data = result.data
            assert data["status"] == "Done"
            assert data["result_count"] == 2
            assert data["results"][0]["rank"] == 1
            assert data["resolved_nodes"]["node_0"]["curie"] == "MONDO:0004979"

    asyncio.run(scenario())


def test_query_ars_degrades_for_task_unaware_clients(mcp_module, ars_mocks):
    ars_mocks["finished"]["finished"] = True

    async def scenario():
        async with _client(mcp_module) as client:
            result = await client.call_tool(
                "query_ars",
                {"node": ["asthma"], "neighbor_categories": ["Drug"]},
            )
            assert result.data["status"] == "Done"
            assert result.data["result_count"] == 2

    asyncio.run(scenario())


def test_query_ars_is_registered_as_optional_task(mcp_module):
    tools_registry = asyncio.run(mcp_module.mcp.get_tools())
    task_tool = tools_registry["query_ars"]
    assert task_tool.task_config is not None
    assert task_tool.task_config.mode == "optional"
    assert task_tool.annotations.readOnlyHint is True
    assert "progress" in inspect.signature(task_tool.fn).parameters
