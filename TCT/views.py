"""Offline views of execution records."""

from collections import Counter, defaultdict
import json


def trace(events):
    """List captured calls with their parent IDs and observation counts."""
    calls = []
    for event in sorted(
        events, key=lambda item: (item["run_id"], item.get("step_id", item["call_id"]))
    ):
        operation = event.get("operation")
        calls.append(
            {
                "run_id": event["run_id"],
                "call_id": event["call_id"],
                "parent_call_id": event.get("parent_call_id"),
                "operation": operation,
                "label": event.get("label", operation),
                "status": event.get("status"),
                "observation_count": len(event.get("observations", [])),
            }
        )
    return {"call_count": len(calls), "calls": calls}


def _service_outcome(observation):
    if observation["status"] != "received":
        return observation["status"]
    code = observation["status_code"]
    if not 200 <= code < 300:
        return "http_error"
    if observation.get("body_json_status") == "not_json":
        return "non_json"
    body = observation.get("body_json")
    if observation.get("service_kind") == "ars_result":
        from .evidence import ars_response

        body = ars_response(body)
    message = body.get("message") if isinstance(body, dict) else None
    is_trapi = observation.get("service_kind") == "trapi" or isinstance(message, dict)
    if (
        is_trapi
        and isinstance(body, dict)
        and (
            body.get("error")
            or body.get("errors")
            or body.get("status") not in (None, "Success", "OK")
        )
    ):
        return "application_error"
    if isinstance(message, dict):
        graph = message.get("knowledge_graph")
        edges = graph.get("edges") if isinstance(graph, dict) else None
        if isinstance(edges, dict):
            return "answered" if edges else "empty"
    return "received"


def providers(events):
    """Summarize service outcomes from captured HTTP observations."""
    from .evidence import ars_exchange

    by_url = {}
    for event in events:
        for observation in event.get("observations", []):
            request = observation.get("request") or {}
            if observation.get("kind") != "service" or not request.get("url"):
                continue
            by_url.setdefault(request["url"], []).append(
                {
                    "run_id": event["run_id"],
                    "call_id": event["call_id"],
                    "method": request.get("method"),
                    "service_kind": observation.get("service_kind"),
                    "outcome": _service_outcome(observation),
                    "status_code": observation.get("status_code"),
                    "error_type": observation.get("error_type"),
                    "elapsed_ms": observation.get("elapsed_ms"),
                    **ars_exchange(observation),
                }
            )
    return {
        "request_count": sum(map(len, by_url.values())),
        "services": [
            {"url": url, "request_count": len(requests), "requests": requests}
            for url, requests in sorted(by_url.items())
        ],
    }


def edges(events):
    """Explain edge provenance for each recorded provider merge."""
    from .evidence import ars_exchange

    merges = []
    for event in events:
        observations = event.get("observations", [])
        inputs = [item for item in observations if item.get("kind") == "merge_input"]
        decisions = [item for item in observations if item.get("kind") == "edge_merge"]
        if not decisions:
            continue

        retained = {}
        for decision in decisions:
            merge_input = inputs[decision["input_index"]]
            provider = merge_input["provider"]
            graph = merge_input["message"]["knowledge_graph"]
            for edge_id, edge in graph["edges"].items():
                provenance = retained.setdefault(edge_id, {"contributors": []})
                provenance["contributors"].append(
                    {
                        "provider": provider,
                        "source_edge_id": edge_id,
                        "sources": edge.get("sources", []),
                    }
                )
                provenance["retained_provider"] = provider

        merges.append(
            {
                "run_id": event["run_id"],
                "call_id": event["call_id"],
                "policy": decisions[-1].get("policy"),
                "edge_count": len(retained),
                "edges": dict(sorted(retained.items())),
            }
        )
    for event, observation, _, payload in _ars_merged_edges(events):
        merges.append(
            {
                "run_id": event["run_id"],
                "call_id": event["call_id"],
                "policy": "ars_merged_response",
                "edge_count": len(payload),
                **ars_exchange(observation),
                "edges": {
                    edge_id: {
                        "retained_provider": "ARS",
                        "contributors": [
                            {
                                "provider": "ARS",
                                "source_edge_id": edge_id,
                                "sources": edge.get("sources", []),
                            }
                        ],
                    }
                    for edge_id, edge in sorted(payload.items())
                },
            }
        )
    return {"merges": merges}


def page(events):
    """Return the self-contained HTML report for a run."""
    from .evidence_page import render_page

    return {"html": render_page(events)}


def _ars_merged_edges(events):
    from .evidence import _ars_query_links, ars_result_source

    queries = _ars_query_links(events)
    for event in events:
        if (
            event.get("status") != "succeeded"
            or event.get("operation") != "fetch_ars_results"
        ):
            continue
        for observation in event.get("observations", []):
            if (
                observation.get("service_kind") != "ars_result"
                or observation.get("status_code") != 200
            ):
                continue
            query, response = ars_result_source(event, observation, queries)
            message = response.get("message") if isinstance(response, dict) else None
            graph = (
                message.get("knowledge_graph") if isinstance(message, dict) else None
            )
            edges = graph.get("edges") if isinstance(graph, dict) else None
            if isinstance(edges, dict) and all(
                isinstance(edge, dict) for edge in edges.values()
            ):
                yield event, observation, query, edges


def _merge_payloads(events):
    from .evidence import canonical, digest

    payloads = defaultdict(Counter)
    for event in events:
        if (
            event.get("operation") != "parallel_api_query"
            or event.get("status") != "succeeded"
        ):
            continue
        output = event.get("output")
        if not isinstance(output, dict):
            continue
        query_hash = digest((event.get("inputs") or {}).get("query_json"))
        for edge_id, edge in output.items():
            payloads[(query_hash, edge_id)][canonical(edge)] += 1
    for _, _, query, edges in _ars_merged_edges(events):
        query_hash = digest(query)
        for edge_id, edge in edges.items():
            payloads[(query_hash, edge_id)][canonical(edge)] += 1
    return payloads


def _request_outcomes(events):
    from .evidence import canonical

    return Counter(
        canonical(
            {
                "url": (
                    request["endpoint"] + "/messages/{pk}"
                    if request.get("endpoint")
                    and request["service_kind"] in ("ars_status", "ars_result")
                    else service["url"]
                ),
                **{
                    key: request[key]
                    for key in (
                        "method",
                        "service_kind",
                        "outcome",
                        "status_code",
                        "error_type",
                    )
                },
            }
        )
        for service in providers(events)["services"]
        for request in service["requests"]
    )


def diff(events, baseline):
    """Compare exact retained edge payloads and HTTP outcomes across recordings."""
    old_edges, new_edges = _merge_payloads(baseline), _merge_payloads(events)
    edge_changes = []
    for query_hash, edge_id in sorted(old_edges.keys() | new_edges.keys()):
        before = old_edges.get((query_hash, edge_id), Counter())
        after = new_edges.get((query_hash, edge_id), Counter())
        if before != after:
            edge_changes.append(
                {
                    "query_hash": query_hash,
                    "edge_id": edge_id,
                    "before": [
                        {"edge": json.loads(edge), "count": count}
                        for edge, count in sorted(before.items())
                    ],
                    "after": [
                        {"edge": json.loads(edge), "count": count}
                        for edge, count in sorted(after.items())
                    ],
                }
            )
    old_requests, new_requests = _request_outcomes(baseline), _request_outcomes(events)
    return {
        "edge_changes": edge_changes,
        "request_changes": [
            {**json.loads(key), "before": old_requests[key], "after": new_requests[key]}
            for key in sorted(old_requests.keys() | new_requests.keys())
            if old_requests[key] != new_requests[key]
        ],
    }


VIEWS = {
    "trace": trace,
    "providers": providers,
    "edges": edges,
    "page": page,
    "diff": diff,
}
