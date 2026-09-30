"""Loss-aware, optional TRAPI representations; never execute or validate queries."""

from copy import deepcopy
from typing import Any


def with_trapi(result: Any, kind: str) -> dict[str, Any]:
    """Keep the native result and attach detached, explicitly unvalidated artifacts.

    These artifacts describe retained data, not schema conformance or biological
    correctness. In particular, merged edges cannot recover provider bindings.
    """
    artifacts = []
    limitations = []

    def add(artifact_kind, content, **metadata):
        artifacts.append(
            {"kind": artifact_kind, "content": deepcopy(content), **metadata}
        )

    if kind == "message":
        if result is None:
            limitations.append(
                "Native result cannot distinguish failure from empty results."
            )
        else:
            add("response", {"message": result})
            limitations.append("Original HTTP response envelope was not retained.")
    elif kind == "finder":
        add("response", {"message": result.raw})
        limitations.append(
            "Finder output is TRAPI-style; path extensions, bindings and auxiliary "
            "graphs may not conform to a TRAPI schema."
        )
    elif kind == "edges":
        add("knowledge_graph_fragment", {"edges": result})
        limitations.append(
            "Only merged edges remain; nodes, result bindings, auxiliary graphs "
            "and provider failures cannot be recovered. This is not a TRAPI response."
        )
    elif kind == "workflow":
        for step_id, step in result["steps"].items():
            if step["op"] != "query":
                continue
            metadata = {"step_id": step_id, "execution_status": step["status"]}
            inputs = step.get("inputs", {})
            if "query" in inputs:
                add("query", inputs["query"], **metadata)
            if "response" in step:
                add("response", step["response"], **metadata)
        limitations.append(
            "Artifacts describe individual query steps. Filters and joins remain "
            "in the evidence bundle; they are not compiled into a single TRAPI query."
        )
    else:
        raise ValueError(f"Unknown TRAPI representation kind: {kind}")
    return {
        "result": result,
        "trapi": {
            "representation_version": 1,
            "schema_validation": "not_performed",
            "artifacts": artifacts,
            "limitations": limitations,
        },
    }
