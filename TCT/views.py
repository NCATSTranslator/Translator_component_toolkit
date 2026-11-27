"""Offline views of execution records."""


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
    return {"merges": merges}


def page(events):
    """Return the self-contained HTML report for a run."""
    from .evidence_page import render_page

    return {"html": render_page(events)}


VIEWS = {"trace": trace, "providers": providers, "edges": edges, "page": page}
