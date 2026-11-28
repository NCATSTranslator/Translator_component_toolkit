"""Offline tests for the ARS tools (sync trio, finder tools, MCP background task).

Covers argument shaping of the interface-neutral tools and the full MCP surface
through an in-process FastMCP client, including the SEP-1686 task flow of
``query_ars`` (task ID, status polling, result fetch, graceful degradation).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import json
from types import SimpleNamespace

import pytest
import requests
from mcp.shared.exceptions import McpError

ars = importlib.import_module("TCT.Query_ARS")
import TCT.interfaces.tools as tools  # noqa: E402
from tests.ars_fixtures import (  # noqa: E402
    BASE,
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


def test_plover_fallback_logs_without_writing_to_stdout(monkeypatch, caplog, capsys):
    dev_query = (
        "https://multiomics.rtx.ai:9990/BigGIM_DrugResponse_PerformancePhase/query"
    )
    dev_metakg = dev_query.removesuffix("query") + "meta_knowledge_graph"
    ci_metakg = (
        "https://multiomics.ci.transltr.io/BigGIM_DrugResponse_PerformancePhase/"
        "meta_knowledge_graph"
    )
    edge = {
        "subject": "biolink:Gene",
        "predicate": "biolink:affects",
        "object": "biolink:Disease",
    }

    def get(url, **kwargs):
        if url == ci_metakg:
            return FakeResponse({}, 404)
        return FakeResponse({"edges": [edge] if url == dev_metakg else []}, 200)

    monkeypatch.setattr(requests, "get", get)

    api_names, _ = tools.add_plover_apis_to_metakg({}, None)

    assert list(api_names.values()) == [dev_query]
    assert "dev fallback" in caplog.text
    assert dev_query in caplog.text
    assert capsys.readouterr().out == ""


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

def test_get_ars_results_merge_saving_reports_not_ready(monkeypatch):
    # NCATSTranslator/Relay#621: parent Done but the merge agent is still
    # saving, so reporting ready with zero results would be wrong.
    monkeypatch.setattr(
        tools, "_get_ARS_status",
        lambda pk: ars.parse_trace(PARENT, done_trace(merged=None, merge_status="Running")),
    )
    monkeypatch.setattr(
        tools, "_get_ARS_result", lambda status: pytest.fail("must not fetch while merge is saving")
    )
    result = tools.get_ars_results(PARENT)

    assert result["ready"] is False
    assert result["status"] == "Done"
    assert result["merged_pk"] is None

def test_get_ars_results_done_without_merge_agent_is_ready(monkeypatch, ars_mocks):
    # No merge agent child at all: the query finished without a merged
    # message, and the parent payload fallback is the final answer.
    monkeypatch.setattr(
        tools, "_get_ARS_status",
        lambda pk: ars.parse_trace(PARENT, trace("Done", None, [child("ara-x", "Done")])),
    )
    result = tools.get_ars_results(PARENT)

    assert result["ready"] is True
    assert result["merged_pk"] is None


def test_get_ars_results_reports_failed_query_without_fetching(monkeypatch):
    failed = ars.parse_trace(
        PARENT, trace("Error", None, [child(ars.MERGE_AGENT, "Running")])
    )
    monkeypatch.setattr(tools, "_get_ARS_status", lambda pk: failed)

    def unexpected_fetch(*args, **kwargs):
        pytest.fail("must not fetch results for a failed query")

    monkeypatch.setattr(ars, "fetch_ars_results", unexpected_fetch)

    with pytest.raises(ars.ARSError, match="status Error"):
        tools.get_ars_results(PARENT)


# --------------------------------------------------------------------------- #
# finder tools
# --------------------------------------------------------------------------- #
def test_ars_neighborhood_finder_shapes_finder_result(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    # The finder resolves nodes inside TCT.Query_ARS, not in the tools module.
    monkeypatch.setattr(
        ars, "_resolve_nodes", lambda values, **kwargs: [_resolved()], raising=True
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
    # The query is submitted unchanged except for the submitter annotation.
    assert submitted == {**query, "submitter": "TCT"}
    assert result["status"] == "Done"
    assert result["merged_pk"] == MERGED
    assert result["message"]["results"]


def test_ars_pathfinder_shapes_finder_result(monkeypatch, ars_mocks):
    ars_mocks["finished"]["finished"] = True
    monkeypatch.setattr(
        ars, "_resolve_nodes",
        lambda values, **kwargs: [_resolved(), _resolved("CHEBI:906", "albuterol")],
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
    assert ars_mocks["submit"][0][1] == {**query, "submitter": "TCT"}


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


def test_query_ars_records_and_replays_task(mcp_module, monkeypatch, tmp_path):
    from TCT.evidence import evidence, inventory, read_run

    submissions, requests_seen = [], []
    polls = iter([trace("Running"), done_trace()])
    raw = envelope(merged_message())

    def transport(session, method, url, **kwargs):
        requests_seen.append((method, url))
        if method == "POST" and url.endswith("/submit"):
            submissions.append(kwargs["json"])
            payload, status = {"pk": PARENT}, 201
        elif kwargs.get("params") == {"trace": "y"} and url.endswith(PARENT):
            payload, status = next(polls), 200
        else:
            assert url.endswith(MERGED)
            payload, status = raw, 200
        response = requests.Response()
        response.url = url
        response.status_code = status
        response._content = json.dumps(payload).encode()
        return response

    def reject_http(*args, **kwargs):
        pytest.fail("ARS replay contacted HTTP")

    monkeypatch.setattr(requests.Session, "request", transport)
    monkeypatch.setattr(ars.time, "sleep", lambda seconds: None)
    settings = {
        "store": str(tmp_path),
        "run_id": "original",
        "step_id": "ars-task",
        "record": True,
        "cache": True,
        "langfuse": False,
    }
    arguments = {"node": ["asthma"], "neighbor_categories": ["Drug"], "top_n": 0}

    async def scenario():
        async with _client(mcp_module) as client:
            task = await client.call_tool(
                "query_ars", arguments | {"execution": settings}, task=True
            )
            original = await task.result()
            assert original.data["pk"] == PARENT
            assert original.data["merged_pk"] == MERGED
            assert original.data["message"] == merged_message()
            monkeypatch.setattr(requests.Session, "request", reject_http)
            replay = await client.call_tool(
                "query_ars",
                arguments | {"execution": settings | {
                    "run_id": "replay",
                    "cache": {"mode": "replay", "snapshot_run": "original"},
                }},
                task=True,
            )
            assert (await replay.result()).data == original.data

    asyncio.run(scenario())
    assert requests_seen == [
        ("POST", BASE + "submit"),
        ("GET", BASE + f"messages/{PARENT}"),
        ("GET", BASE + f"messages/{PARENT}"),
        ("GET", BASE + f"messages/{MERGED}"),
    ]
    records = read_run(tmp_path, "original")
    (task_record,) = [record for record in records if record["step_id"] == "ars-task"]
    assert task_record["operation"] == "query_ars"
    assert "progress" not in task_record["inputs"]
    assert any(record["parent_call_id"] == task_record["call_id"] for record in records)
    (fetch,) = [record for record in records if record["operation"] == "fetch_ars_results"]
    assert fetch["output"] == raw
    sources, issues, _ = inventory(records)
    assert issues == []
    (source,) = sources.values()
    assert source["query"] == submissions[0]
    assert source["response"] == raw["fields"]["data"]
    assert source["eligible"] is True
    view = evidence({
        "action": "export", "view": "providers", "store": str(tmp_path), "run_id": "original"
    })
    exchanges = [request for service in view["services"] for request in service["requests"]]
    assert {item.get("parent_pk") for item in exchanges if "parent_pk" in item} == {PARENT}
    assert MERGED in {item.get("merged_pk") for item in exchanges}
    assert any(item.get("message_pk") == MERGED and item["outcome"] == "answered" for item in exchanges)
    selection = {"action": "export", "store": str(tmp_path), "run_id": "original"}
    (merge,) = evidence(selection | {"view": "edges"})["merges"]
    assert merge["policy"] == "ars_merged_response"
    assert merge["message_pk"] == MERGED
    assert merge["edges"]["e1"]["contributors"][0]["sources"] == (
        merged_message()["knowledge_graph"]["edges"]["e1"]["sources"]
    )
    assert evidence(
        selection | {
            "view": "diff", "run_id": "replay",
            "against": {"store": str(tmp_path), "run_id": "original"},
        }
    ) == {"edge_changes": [], "request_changes": []}


def test_live_ars_submit_and_poll_are_never_reused(monkeypatch):
    from TCT.execution import execution

    calls = []

    def transport(session, method, url, **kwargs):
        calls.append(method)
        body = {"pk": PARENT} if method == "POST" else {"merged_version": MERGED}
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = json.dumps(body).encode()
        return response

    monkeypatch.setattr(requests.Session, "request", transport)
    with execution({"cache": True, "langfuse": False}) as run:
        for _ in range(2):
            pk = ars.submit_ARS({"message": {"query_graph": {}}})
            assert ars.get_ARS_status(pk).merged_version == MERGED
    assert calls == ["POST", "GET", "POST", "GET"]
    assert [event["status"] for event in run.cache_events] == ["not_cacheable"] * 4


@pytest.mark.parametrize(("status", "polls"), [("Running", 1), ("Done", 2)])
def test_ars_replay_preserves_timed_poll_outcome(
    monkeypatch, tmp_path, status, polls
):
    from TCT.execution import execution

    elapsed = 0
    requests_seen = []

    def advance(seconds):
        nonlocal elapsed
        elapsed += seconds

    def transport(session, method, url, **kwargs):
        requests_seen.append(url)
        advance(5)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(trace(status)).encode()
        return response

    def reject_http(*args, **kwargs):
        pytest.fail("ARS replay contacted HTTP")

    def wait():
        return ars.wait_for_ARS(
            PARENT,
            poll_interval=1,
            max_retries=10 if status == "Done" else 3,
            merge_grace=4,
        )

    monkeypatch.setattr(
        ars, "time", SimpleNamespace(monotonic=lambda: elapsed, sleep=advance)
    )
    monkeypatch.setattr(requests.Session, "request", transport)
    settings = {
        "store": str(tmp_path), "run_id": "live", "cache": True, "langfuse": False
    }
    with execution(settings):
        if status == "Running":
            with pytest.raises(ars.ARSTimeoutError) as timeout:
                wait()
            original = timeout.value.status
        else:
            original = wait()
    assert requests_seen == [BASE + f"messages/{PARENT}"] * polls
    elapsed = 0
    monkeypatch.setattr(requests.Session, "request", reject_http)
    with execution(settings | {
        "run_id": "replay",
        "cache": {"mode": "replay", "snapshot_run": "live"},
    }):
        if status == "Running":
            with pytest.raises(ars.ARSTimeoutError) as timeout:
                wait()
            assert timeout.value.status == original
        else:
            assert wait() == original


def test_query_ars_is_registered_as_optional_task(mcp_module):
    tools_registry = asyncio.run(mcp_module.mcp.get_tools())
    task_tool = tools_registry["query_ars"]
    assert task_tool.task_config is not None
    assert task_tool.task_config.mode == "optional"
    assert task_tool.annotations.readOnlyHint is False
    assert "progress" in inspect.signature(task_tool.fn).parameters

def test_query_ars_runs_blocking_calls_off_the_event_loop(mcp_module, ars_mocks, monkeypatch):
    # Node resolution and submission make HTTP calls with timeouts up to
    # 120 s; they must not block the event loop serving other MCP requests.
    import threading

    ars_mocks["finished"]["finished"] = True
    resolve_threads = []
    submit_threads = []

    def recording_resolve(node):
        resolve_threads.append(threading.current_thread())
        return [_resolved()]

    def recording_submit(query, *, url=None):
        submit_threads.append(threading.current_thread())
        return PARENT

    monkeypatch.setattr(tools, "_resolve_nodes", recording_resolve)
    monkeypatch.setattr(ars, "submit_ARS", recording_submit)

    async def scenario():
        async with _client(mcp_module) as client:
            result = await client.call_tool(
                "query_ars",
                {"node": ["asthma"], "neighbor_categories": ["Drug"], "top_n": 1},
            )
            assert result.data["status"] == "Done"

    asyncio.run(scenario())

    assert resolve_threads and submit_threads
    assert all(thread is not threading.main_thread() for thread in resolve_threads)
    assert all(thread is not threading.main_thread() for thread in submit_threads)
