"""Regression coverage for deterministic per-turn telemetry benchmarks."""

import json
from pathlib import Path

from benchmarks.langfuse_turns import benchmark_report


def test_turn_benchmark_exposes_batching_and_duplicate_calls():
    report = benchmark_report()
    turns = report["turns"]

    assert turns["one_call_per_identifier"]["tool_calls"] == 7
    assert turns["batched_identifiers"]["tool_calls"] == 1
    assert turns["duplicate_batched_calls"]["repeated_input_calls"] == 1
    assert report["batching_comparison"]["tool_calls_avoided"] == 6
    assert report["batching_comparison"]["input_bytes_avoided"] > 0
    assert report["batching_comparison"]["provider_metadata_bytes_avoided"] > 0


def test_checked_in_turn_baseline_matches_the_benchmark():
    baseline_path = (
        Path(__file__).parents[1] / "benchmarks" / "langfuse_turns_baseline.json"
    )

    assert json.loads(baseline_path.read_text()) == benchmark_report()
