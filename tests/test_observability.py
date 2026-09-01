"""Tests for optional Langfuse instrumentation at interface boundaries."""

from contextlib import contextmanager

import pytest

from TCT.interfaces import invocation, observability
from TCT.interfaces.invocation import ToolInvocationError


def test_langfuse_activation_is_explicit_and_false_by_default():
    """Credentials alone do not trace; the TCT switch is required."""
    credentials = {
        "LANGFUSE_PUBLIC_KEY": "public",
        "LANGFUSE_SECRET_KEY": "secret",
    }

    assert observability.langfuse_enabled(credentials) is False
    assert observability.langfuse_enabled(
        {**credentials, "TCT_LANGFUSE_ENABLED": "false"}
    ) is False
    assert observability.langfuse_enabled({"TCT_LANGFUSE_ENABLED": "yes"}) is True
    assert observability.langfuse_enabled({}) is False


def test_invalid_langfuse_activation_value_is_actionable():
    """Configuration mistakes fail with the relevant variable name."""
    with pytest.raises(
        observability.ObservabilityConfigurationError,
        match="TCT_LANGFUSE_ENABLED",
    ):
        observability.langfuse_enabled({"TCT_LANGFUSE_ENABLED": "perhaps"})


def test_enabled_tracing_requires_only_the_optional_install(monkeypatch):
    """A base installation imports normally and explains an enabled missing SDK."""
    monkeypatch.setenv("TCT_LANGFUSE_ENABLED", "true")

    def missing_langfuse(name):
        raise ModuleNotFoundError(name="langfuse")

    monkeypatch.setattr(observability.importlib, "import_module", missing_langfuse)

    with pytest.raises(
        observability.ObservabilityConfigurationError,
        match="install TCT with the 'langfuse' extra",
    ):
        with observability.observe_tool(
            name="tct.tool.example",
            input_factory=dict,
            metadata={},
        ):
            pass


def test_invoke_records_tool_input_output_and_interface(monkeypatch):
    """One boundary supplies Langfuse data for every registered callable."""
    captured = {}

    class Observation:
        def update(self, **values):
            captured["update"] = values

    @contextmanager
    def fake_observe_tool(*, name, input_factory, metadata):
        captured.update(
            name=name,
            input=input_factory(),
            metadata=metadata,
        )
        yield Observation()

    monkeypatch.setattr(invocation, "observe_tool", fake_observe_tool)

    def combine(left: str, right: str = "default") -> tuple[str, str]:
        return left, right

    result = invocation.invoke(combine, "value", _interface="mcp")

    assert result == ("value", "default")
    assert captured["name"] == "tct.tool.combine"
    assert captured["input"] == {"left": "value", "right": "default"}
    assert captured["metadata"] == {
        "tct.interface": "mcp",
        "tct.module": __name__,
        "tct.tool": "combine",
        **invocation._input_metadata(captured["input"]),
    }
    assert captured["update"] == {
        "output": ["value", "default"],
        "metadata": invocation._payload_metadata(
            "tct.output", ["value", "default"]
        ),
    }


def test_tool_telemetry_identifies_duplicates_and_batching_opportunities(monkeypatch):
    """Stable hashes and query counts expose repeated and under-batched calls."""
    observations = []

    class Observation:
        def update(self, **values):
            observations[-1]["update"] = values

    @contextmanager
    def fake_observe_tool(*, name, input_factory, metadata):
        observations.append({"name": name, "input": input_factory(), "metadata": metadata})
        yield Observation()

    monkeypatch.setattr(invocation, "observe_tool", fake_observe_tool)

    def query_provider(api_name: str, query_json: dict) -> dict:
        return {"results": [1, 2]}

    query = {
        "message": {
            "query_graph": {
                "nodes": {
                    "genes": {"ids": ["NCBIGene:1", "NCBIGene:2"]},
                    "disease": {"ids": ["MONDO:1"]},
                }
            }
        }
    }

    invocation.invoke(query_provider, "RTX KG2", query, _interface="mcp")
    invocation.invoke(query_provider, "RTX KG2", query, _interface="mcp")

    first = observations[0]["metadata"]
    second = observations[1]["metadata"]
    assert first["tct.provider.name"] == "RTX KG2"
    assert first["tct.query.node_count"] == 2
    assert first["tct.query.identifier_count"] == 3
    assert first["tct.query.identifier_node_count"] == 2
    assert first["tct.input.sha256"] == second["tct.input.sha256"]
    assert (
        first["tct.input.argument.query_json.sha256"]
        == second["tct.input.argument.query_json.sha256"]
    )
    assert observations[0]["update"]["metadata"]["tct.output.bytes"] > 0


def test_tool_errors_cross_the_observation_before_normalization(monkeypatch):
    """Langfuse sees the original exception while adapters keep stable errors."""
    captured = {}

    @contextmanager
    def fake_observe_tool(**kwargs):
        try:
            yield object()
        except Exception as error:
            captured["error"] = error
            raise

    monkeypatch.setattr(invocation, "observe_tool", fake_observe_tool)
    cause = ValueError("failed")

    def fail() -> None:
        raise cause

    with pytest.raises(ToolInvocationError) as error:
        invocation.invoke(fail, _interface="cli")

    assert captured["error"] is cause
    assert error.value.cause is cause


def test_disabled_observability_does_not_evaluate_trace_input(monkeypatch):
    """Untraced core/interface calls avoid serialization work and SDK imports."""
    monkeypatch.delenv("TCT_LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    class Value:
        def to_dict(self):
            raise AssertionError("trace input should not be serialized")

    def identity(value):
        return value

    value = Value()
    assert invocation.invoke(identity, value) is value
