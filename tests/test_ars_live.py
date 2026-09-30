"""Live ARS tests, enabled only with ``TCT_LIVE_ARS=1``.

Includes the fixture-drift test: it captures a real ARS trace and merged
envelope, then asserts the offline fixtures in ``tests/ars_fixtures.py``
remain a structural subset of the live responses. Skipped entirely without
the environment variable so the default suite stays offline.
"""

from __future__ import annotations

import os

import pytest

from TCT import ARS_neighborhood_finder, ARS_pathfinder
from TCT import Query_ARS as ars_module
from TCT.TCT import FinderResult

ars = ars_module
from tests.ars_fixtures import (  # noqa: E402
    child,
    done_trace,
    envelope,
    merged_message,
    trace,
)

pytestmark = pytest.mark.skipif(
    os.getenv("TCT_LIVE_ARS") != "1",
    reason="live ARS checks run only with TCT_LIVE_ARS=1",
)


def test_live_ARS_neighborhood_finder_returns_finder_shaped_result():
    # No predicate filter: the ARS accepts the query but some directional
    # predicates (e.g. biolink:treated_by) come back with an empty merge.
    result = ARS_neighborhood_finder("asthma", ["ChemicalEntity"])

    assert isinstance(result, ars.ARSResult)
    assert isinstance(result, FinderResult)
    assert result.status is not None and result.status.status == "Done"
    assert result.results, "expected at least one merged result"
    rows = result.summarize(3)
    # essence is optional in ARS merges (aragorn/bte leave it unset).
    assert rows and rows[0]["rank"] == 1 and rows[0]["nodes"]


def test_live_ARS_pathfinder_returns_paths():
    result = ARS_pathfinder("asthma", "albuterol", intermediate_categories=["Gene"])

    assert isinstance(result, ars.ARSResult)
    assert result.status is not None and result.status.status == "Done"
    assert result.results, "expected at least one merged path result"


# --------------------------------------------------------------------------- #
# fixture drift
# --------------------------------------------------------------------------- #
def _subset_structure(offline, live, path, problems):
    """Assert the offline fixture's structure is contained in the live value."""
    if isinstance(offline, dict):
        if not isinstance(live, dict):
            problems.append(f"{path}: expected object, got {type(live).__name__}")
            return
        for key, value in offline.items():
            if key == "*":
                # Wildcard: compare the value shape against any one live entry.
                if not live:
                    problems.append(f"{path}: empty live object")
                else:
                    first = next(iter(live))
                    _subset_structure(value, live[first], f"{path}.{first}", problems)
            elif key not in live:
                problems.append(f"{path}.{key}: missing in live response")
            else:
                _subset_structure(value, live[key], f"{path}.{key}", problems)
    elif isinstance(offline, list):
        if not isinstance(live, list):
            problems.append(f"{path}: expected list, got {type(live).__name__}")
            return
        if not offline:
            return
        # Lists are compared by their first element: fixtures carry one
        # representative entry.
        if not live:
            problems.append(f"{path}: empty live list")
        else:
            _subset_structure(offline[0], live[0], f"{path}[0]", problems)
    elif offline is not None and not isinstance(live, type(offline)):
        problems.append(
            f"{path}: type {type(live).__name__} does not match fixture type "
            f"{type(offline).__name__}"
        )


def test_offline_fixtures_match_live_ars_shape():
    """The offline fixtures must not drift from the real ARS response shape."""
    import requests

    session = requests.Session()
    root = ars._ars_root(None)

    pk = session.post(f"{root}/submit", json=ars.format_query_json_forARS_neighborhood(
        subject_ids=["MONDO:0004979"],
        object_categories=["biolink:ChemicalEntity"],
    ), timeout=ars.HTTP_TIMEOUT).json()["pk"]

    merged_pk = ars.check_ars_results(pk)
    live_trace = session.get(
        f"{root}/messages/{pk}", params={"trace": "y"}, timeout=ars.HTTP_TIMEOUT
    ).json()
    live_envelope = session.get(
        f"{root}/messages/{merged_pk or pk}", timeout=ars.HTTP_TIMEOUT
    ).json()

    problems: list[str] = []
    _subset_structure(trace("Done"), live_trace, "trace", problems)
    _subset_structure(
        done_trace(merged=merged_pk or "x"),
        live_trace,
        "done_trace",
        problems,
    )
    if not any("merged_version" in problem for problem in problems):
        _subset_structure(
            done_trace()["children"][0],
            live_trace["children"][0] if live_trace.get("children") else child("x", "Done"),
            "children[0]",
            problems,
        )
    fixture_envelope = envelope(merged_message())
    kg = fixture_envelope["fields"]["data"]["message"]["knowledge_graph"]
    # Node and edge ids vary per query; compare their entry shapes instead.
    kg["nodes"] = {"*": next(iter(merged_message()["knowledge_graph"]["nodes"].values()))}
    kg["edges"] = {"*": next(iter(merged_message()["knowledge_graph"]["edges"].values()))}
    _subset_structure(fixture_envelope, live_envelope, "envelope", problems)

    assert not problems, (
        "offline ARS fixtures drifted from the live response shape:\n"
        + "\n".join(sorted(set(problems)))
    )

# --------------------------------------------------------------------------- #
# live MCP flow
# --------------------------------------------------------------------------- #
def test_live_mcp_ars_tools_full_flow():
    """submit_ars_query, poll get_ars_status, then fetch ranked results."""
    import TCT.interfaces.tools as tools

    submitted = tools.submit_ars_query(["asthma"], ["ChemicalEntity"])
    pk = submitted["pk"]
    assert pk and submitted["status"] in {"Running", "Done"}

    deadline = 900.0
    import time

    start = time.monotonic()
    status = tools.get_ars_status(pk)
    while not status.is_terminal and time.monotonic() - start < deadline:
        time.sleep(15.0)
        status = tools.get_ars_status(pk)

    assert status.status == "Done", f"ARS did not finish: {status.summary()}"
    result = tools.get_ars_results(pk, top_n=5)
    assert result["ready"] is True
    assert result["status"] == "Done"
    assert result["merged_pk"], "expected a merged message pk"
    rows = result["results"]
    assert rows and rows[0]["rank"] == 1

def _fresh_mcp_module():
    """Reload the adapter so each client gets a pristine FastMCP instance.

    FastMCP keeps dependency/session state on the server object; reusing one
    instance across a task call and a plain call fails dependency resolution.
    """
    import importlib

    from TCT.interfaces import mcp as mcp_module

    return importlib.reload(mcp_module)

def test_live_mcp_query_ars_background_task():
    """query_ars end to end through an in-process MCP client as a task."""
    import asyncio

    from fastmcp import Client

    async def scenario():
        async with Client(mcp_module.mcp) as client:
            task = await client.call_tool(
                "query_ars",
                {"node": ["asthma"], "neighbor_categories": ["ChemicalEntity"], "top_n": 3},
                task=True,
            )
            result = await task.result()
            data = result.data
            assert data is not None
            assert data["status"] == "Done"
            assert data["result_count"] >= 1
            assert data["results"] and data["results"][0]["rank"] == 1
            return data

    mcp_module = _fresh_mcp_module()
    data = asyncio.run(scenario())
    assert isinstance(data, dict)

def test_live_mcp_query_ars_task_unaware_client():
    """The same tool also answers a plain (blocking) call."""
    import asyncio

    from fastmcp import Client

    mcp_module = _fresh_mcp_module()

    async def scenario():
        async with Client(mcp_module.mcp) as client:
            return await client.call_tool(
                "query_ars",
                {"node": ["asthma"], "neighbor_categories": ["ChemicalEntity"], "top_n": 3},
            )

    result = asyncio.run(scenario())
    data = result.data
    assert data is not None and data["status"] == "Done"
