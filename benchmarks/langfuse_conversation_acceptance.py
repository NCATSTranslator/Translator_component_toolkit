"""Live Langfuse acceptance probe for conversational-turn metrics.

Unlike ``langfuse_turns.py``, this uploads two agent turns to a real Langfuse
project and builds its report from observations read back through the API.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from benchmarks.langfuse_turns import (
    API_NAMES,
    API_PREDICATES,
    IDENTIFIERS,
    _fixture_query_provider,
    _query,
)


TURN_NAME = "TCT acceptance conversational turn"
REQUIRED_ENVIRONMENT = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
EXPECTED_METRICS = {
    "one_call_per_identifier": {
        "agent_turns_returned": 1,
        "tool_observations_returned": 7,
        "query_identifiers": 14,
    },
    "batched_identifiers": {
        "agent_turns_returned": 1,
        "tool_observations_returned": 1,
        "query_identifiers": 8,
    },
}


class AcceptanceConfigurationError(RuntimeError):
    """Report missing configuration needed for a live acceptance run."""


def validate_environment(environ: Mapping[str, str]) -> None:
    """Require credentials without ever including their values in errors."""
    missing = [name for name in REQUIRED_ENVIRONMENT if not environ.get(name)]
    if missing:
        raise AcceptanceConfigurationError(
            "Live Langfuse acceptance requires: " + ", ".join(missing)
        )


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump(mode="json")
    to_dict = getattr(value, "dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Cannot normalize Langfuse response type {type(value).__name__}")


def _observation_data(response: Any) -> list[dict[str, Any]]:
    data = response.get("data", []) if isinstance(response, Mapping) else response.data
    return [_as_dict(item) for item in data]


def summarize_returned_turn(
    observations: list[dict[str, Any]],
    *,
    trace_id: str,
    scenario: str,
) -> dict[str, Any]:
    """Derive acceptance metrics exclusively from API-returned observations."""
    roots = [item for item in observations if item.get("name") == TURN_NAME]
    tools = [
        item
        for item in observations
        if item.get("name") == "tct.tool._fixture_query_provider"
    ]
    hashes = Counter(
        item.get("metadata", {}).get("tct.input.sha256")
        for item in tools
        if item.get("metadata", {}).get("tct.input.sha256")
    )
    return {
        "scenario": scenario,
        "trace_id": trace_id,
        "agent_turns_returned": len(roots),
        "tool_observations_returned": len(tools),
        "input_bytes": sum(
            item.get("metadata", {}).get("tct.input.bytes", 0) for item in tools
        ),
        "output_bytes": sum(
            item.get("metadata", {}).get("tct.output.bytes", 0) for item in tools
        ),
        "query_identifiers": sum(
            item.get("metadata", {}).get("tct.query.identifier_count", 0)
            for item in tools
        ),
        "unique_tool_inputs": len(hashes),
        "repeated_tool_inputs": sum(count - 1 for count in hashes.values()),
    }


def _run_turn(client: Any, run_id: str, scenario: str, calls: list[list[str]]) -> str:
    from TCT.interfaces import invocation

    with client.start_as_current_observation(
        as_type="agent",
        name=TURN_NAME,
        input={"scenario": scenario, "identifier_count": len(IDENTIFIERS)},
        metadata={
            "tct.acceptance": True,
            "tct.acceptance.run_id": run_id,
            "tct.acceptance.scenario": scenario,
        },
    ) as turn:
        trace_id = turn.trace_id
        results = []
        for identifiers in calls:
            results.append(
                invocation.invoke(
                    _fixture_query_provider,
                    "Fixture KP 0",
                    _query(identifiers),
                    API_NAMES,
                    API_PREDICATES,
                    _interface="acceptance",
                )
            )
        turn.update(output={"tool_calls": len(results), "status": "complete"})
    return trace_id


def _read_back(
    client: Any,
    trace_ids: Mapping[str, str],
    *,
    timeout_seconds: float,
) -> dict[str, list[dict[str, Any]]]:
    deadline = time.monotonic() + timeout_seconds
    pending = dict(trace_ids)
    returned: dict[str, list[dict[str, Any]]] = {}
    while pending and time.monotonic() < deadline:
        for scenario, trace_id in list(pending.items()):
            response = client.api.observations.get_many(
                trace_id=trace_id,
                fields="basic,metadata,metrics",
                limit=100,
            )
            observations = _observation_data(response)
            has_turn = any(item.get("name") == TURN_NAME for item in observations)
            has_tool = any(
                item.get("name") == "tct.tool._fixture_query_provider"
                for item in observations
            )
            if has_turn and has_tool:
                returned[scenario] = observations
                del pending[scenario]
        if pending:
            time.sleep(1)
    if pending:
        names = ", ".join(sorted(pending))
        raise TimeoutError(
            f"Langfuse did not return complete observations within "
            f"{timeout_seconds:g}s for: {names}"
        )
    return returned


def validate_returned_metrics(turns: Mapping[str, Mapping[str, Any]]) -> None:
    """Reject partial read-backs and observations missing payload metrics."""
    problems = []
    for scenario, expected in EXPECTED_METRICS.items():
        actual = turns[scenario]
        for metric, expected_value in expected.items():
            if actual[metric] != expected_value:
                problems.append(
                    f"{scenario}.{metric}={actual[metric]!r} "
                    f"(expected {expected_value!r})"
                )
        for metric in ("input_bytes", "output_bytes", "unique_tool_inputs"):
            if actual[metric] <= 0:
                problems.append(f"{scenario}.{metric} is not positive")
    if problems:
        raise RuntimeError("Invalid Langfuse metric read-back: " + "; ".join(problems))


def run_acceptance(timeout_seconds: float = 30) -> dict[str, Any]:
    """Upload conversational turns, read them back, and return their metrics."""
    validate_environment(os.environ)
    os.environ["TCT_LANGFUSE_ENABLED"] = "true"

    from langfuse import get_client

    client = get_client()
    run_id = str(uuid.uuid4())
    scenarios = {
        "one_call_per_identifier": [[identifier] for identifier in IDENTIFIERS],
        "batched_identifiers": [IDENTIFIERS],
    }
    trace_ids = {
        scenario: _run_turn(client, run_id, scenario, calls)
        for scenario, calls in scenarios.items()
    }
    client.flush()
    returned = _read_back(client, trace_ids, timeout_seconds=timeout_seconds)
    turns = {
        scenario: summarize_returned_turn(
            returned[scenario], trace_id=trace_id, scenario=scenario
        )
        for scenario, trace_id in trace_ids.items()
    }
    validate_returned_metrics(turns)
    one_by_one = turns["one_call_per_identifier"]
    batched = turns["batched_identifiers"]
    return {
        "acceptance": "passed",
        "source": "Langfuse observations API",
        "run_id": run_id,
        "read_back_at": datetime.now(timezone.utc).isoformat(),
        "turns": turns,
        "comparison": {
            "tool_calls_avoided": (
                one_by_one["tool_observations_returned"]
                - batched["tool_observations_returned"]
            ),
            "input_bytes_avoided": (
                one_by_one["input_bytes"] - batched["input_bytes"]
            ),
            "output_bytes_avoided": (
                one_by_one["output_bytes"] - batched["output_bytes"]
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=30)
    arguments = parser.parse_args()
    try:
        report = run_acceptance(arguments.timeout)
    except (AcceptanceConfigurationError, RuntimeError, TimeoutError) as error:
        parser.exit(2, f"acceptance failed: {error}\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
