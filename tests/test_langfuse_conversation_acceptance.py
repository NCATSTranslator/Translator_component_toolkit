from benchmarks.langfuse_conversation_acceptance import (
    AcceptanceConfigurationError,
    TURN_NAME,
    summarize_returned_turn,
    validate_environment,
    validate_returned_metrics,
)


def test_live_acceptance_requires_credentials_without_disclosing_values():
    try:
        validate_environment({"LANGFUSE_PUBLIC_KEY": "pk-secret-value"})
    except AcceptanceConfigurationError as error:
        message = str(error)
    else:
        raise AssertionError("Expected missing secret key to fail")

    assert "LANGFUSE_SECRET_KEY" in message
    assert "pk-secret-value" not in message


def test_summarizes_metrics_returned_by_langfuse():
    observations = [
        {"name": TURN_NAME, "metadata": {"tct.acceptance": True}},
        {
            "name": "tct.tool._fixture_query_provider",
            "metadata": {
                "tct.input.bytes": 100,
                "tct.output.bytes": 20,
                "tct.query.identifier_count": 3,
                "tct.input.sha256": "same",
            },
        },
        {
            "name": "tct.tool._fixture_query_provider",
            "metadata": {
                "tct.input.bytes": 100,
                "tct.output.bytes": 20,
                "tct.query.identifier_count": 3,
                "tct.input.sha256": "same",
            },
        },
    ]

    metrics = summarize_returned_turn(
        observations,
        trace_id="abc123",
        scenario="duplicate",
    )

    assert metrics == {
        "scenario": "duplicate",
        "trace_id": "abc123",
        "agent_turns_returned": 1,
        "tool_observations_returned": 2,
        "input_bytes": 200,
        "output_bytes": 40,
        "query_identifiers": 6,
        "unique_tool_inputs": 1,
        "repeated_tool_inputs": 1,
    }


def test_rejects_a_read_back_without_payload_metrics():
    turns = {
        "one_call_per_identifier": {
            "agent_turns_returned": 1,
            "tool_observations_returned": 7,
            "query_identifiers": 14,
            "input_bytes": 0,
            "output_bytes": 0,
            "unique_tool_inputs": 0,
        },
        "batched_identifiers": {
            "agent_turns_returned": 1,
            "tool_observations_returned": 1,
            "query_identifiers": 8,
            "input_bytes": 0,
            "output_bytes": 0,
            "unique_tool_inputs": 0,
        },
    }

    try:
        validate_returned_metrics(turns)
    except RuntimeError as error:
        assert "input_bytes is not positive" in str(error)
    else:
        raise AssertionError("Expected missing returned metrics to fail acceptance")
