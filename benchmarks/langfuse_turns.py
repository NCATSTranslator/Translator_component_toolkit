"""Deterministic per-turn benchmarks for TCT's Langfuse telemetry contract.

The scenarios use in-memory tool functions and observations. They make no
network requests and send no data to Langfuse.
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager
from typing import Any

from TCT.interfaces import invocation


IDENTIFIERS = [f"NCBIGene:{1000 + index}" for index in range(7)]
API_NAMES = {
    f"Fixture KP {index}": f"https://kp-{index}.example/query" for index in range(12)
}
API_PREDICATES = {name: ["biolink:related_to", "biolink:treats"] for name in API_NAMES}


def _query(identifier_values: list[str]) -> dict[str, Any]:
    return {
        "message": {
            "query_graph": {
                "nodes": {
                    "genes": {"ids": identifier_values},
                    "disease": {"ids": ["MONDO:0005148"]},
                },
                "edges": {
                    "e0": {
                        "subject": "disease",
                        "object": "genes",
                        "predicates": ["biolink:related_to"],
                    }
                },
            }
        }
    }


def _fixture_query_provider(
    api_name: str,
    query_json: dict[str, Any],
    api_names: dict[str, str],
    api_predicates: dict[str, list[str]],
) -> dict[str, Any]:
    identifiers = query_json["message"]["query_graph"]["nodes"]["genes"]["ids"]
    return {
        "provider": api_name,
        "nodes": {
            identifier: {"name": f"fixture result for {identifier}"}
            for identifier in identifiers
        },
    }


def _collect_turn(calls: list[list[str]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []

    class Observation:
        def __init__(self, record: dict[str, Any]) -> None:
            self.record = record

        def update(self, **values: Any) -> None:
            self.record["update"] = values

    @contextmanager
    def collect_observation(*, name, input_factory, metadata):
        input_value = input_factory()
        record = {
            "name": name,
            "input": input_value,
            "metadata": dict(metadata),
        }
        records.append(record)
        yield Observation(record)

    original_observer = invocation.observe_tool
    invocation.observe_tool = collect_observation
    try:
        for identifiers in calls:
            invocation.invoke(
                _fixture_query_provider,
                "Fixture KP 0",
                _query(identifiers),
                API_NAMES,
                API_PREDICATES,
                _interface="mcp",
            )
    finally:
        invocation.observe_tool = original_observer

    hashes = Counter(record["metadata"]["tct.input.sha256"] for record in records)
    input_bytes = sum(record["metadata"]["tct.input.bytes"] for record in records)
    output_bytes = sum(
        record["update"]["metadata"]["tct.output.bytes"] for record in records
    )
    return {
        "tool_calls": len(records),
        "unique_inputs": len(hashes),
        "repeated_input_calls": sum(count - 1 for count in hashes.values()),
        "input_bytes": input_bytes,
        "output_bytes": output_bytes,
        "total_payload_bytes": input_bytes + output_bytes,
        "query_identifiers": sum(
            record["metadata"]["tct.query.identifier_count"] for record in records
        ),
        "provider_metadata_bytes": sum(
            record["metadata"]["tct.input.argument.api_names.bytes"]
            + record["metadata"]["tct.input.argument.api_predicates.bytes"]
            for record in records
        ),
    }


def benchmark_report() -> dict[str, Any]:
    """Compare representative agent-turn tool-call shapes."""
    one_by_one = _collect_turn([[identifier] for identifier in IDENTIFIERS])
    batched = _collect_turn([IDENTIFIERS])
    duplicate = _collect_turn([IDENTIFIERS, IDENTIFIERS])
    input_bytes_avoided = one_by_one["input_bytes"] - batched["input_bytes"]
    total_bytes_avoided = (
        one_by_one["total_payload_bytes"] - batched["total_payload_bytes"]
    )

    return {
        "fixture": "langfuse-turns-v1",
        "notes": {
            "network_requests": 0,
            "langfuse_uploads": 0,
            "token_counts": (
                "Model tokens and price belong to the parent Langfuse generation; "
                "this report measures TCT tool payloads within each turn."
            ),
        },
        "turns": {
            "one_call_per_identifier": one_by_one,
            "batched_identifiers": batched,
            "duplicate_batched_calls": duplicate,
        },
        "batching_comparison": {
            "tool_calls_avoided": one_by_one["tool_calls"] - batched["tool_calls"],
            "input_bytes_avoided": input_bytes_avoided,
            "input_bytes_reduction_percent": round(
                input_bytes_avoided / one_by_one["input_bytes"] * 100,
                1,
            ),
            "total_payload_bytes_avoided": total_bytes_avoided,
            "total_payload_bytes_reduction_percent": round(
                total_bytes_avoided / one_by_one["total_payload_bytes"] * 100,
                1,
            ),
            "provider_metadata_bytes_avoided": (
                one_by_one["provider_metadata_bytes"]
                - batched["provider_metadata_bytes"]
            ),
        },
    }


if __name__ == "__main__":
    print(json.dumps(benchmark_report(), indent=2, sort_keys=True))
