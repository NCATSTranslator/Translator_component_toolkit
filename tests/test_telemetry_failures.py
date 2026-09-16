"""Telemetry must not change execution, results, or original tool errors."""

import subprocess
import sys

import pytest

from TCT.interfaces import cli, invocation, observability, telemetry


@pytest.mark.parametrize("enabled", ["true", "invalid"])
def test_optional_configuration_failure_preserves_tool(monkeypatch, caplog, enabled):
    monkeypatch.setenv("TCT_LANGFUSE_ENABLED", enabled)

    def missing_sdk(name):
        raise ModuleNotFoundError(name="langfuse")

    monkeypatch.setattr(observability.importlib, "import_module", missing_sdk)
    assert invocation.invoke(lambda: "usable") == "usable"
    assert "Unable to start tool observation" in caplog.text


@pytest.mark.parametrize("phase", ["client", "input", "start", "enter", "update", "exit"])
def test_telemetry_failure_preserves_success(monkeypatch, caplog, phase):
    calls = []
    result = {"ok": True}

    def fail_at(stage):
        if phase == stage:
            raise RuntimeError("private telemetry payload")

    class Client:
        def start_as_current_observation(self, **kwargs):
            fail_at("start")
            return self

        def __enter__(self):
            fail_at("enter")
            return self

        def update(self, **kwargs):
            fail_at("update")

        def __exit__(self, *args):
            fail_at("exit")

    def get_client():
        fail_at("client")
        return Client()

    def input_metrics(value):
        fail_at("input")
        return {}

    def tool():
        calls.append(1)
        return result

    monkeypatch.setattr(observability, "_get_langfuse_client", get_client)
    monkeypatch.setattr(telemetry, "_input_metadata", input_metrics)
    assert invocation.invoke(tool) is result
    assert calls == [1]
    assert "Unable to" in caplog.text
    assert "private telemetry payload" not in caplog.text


@pytest.mark.parametrize("exit_behavior", ["raise", "suppress"])
def test_original_tool_error_survives_sdk_cleanup(monkeypatch, exit_behavior):
    original = ValueError("original tool failure")
    seen = []

    class Client:
        def start_as_current_observation(self, **kwargs):
            return self

        def __enter__(self):
            return self

        def __exit__(self, kind, error, traceback):
            seen.append(error)
            if exit_behavior == "raise":
                raise RuntimeError("SDK cleanup failure")
            return True

    def tool():
        raise original

    monkeypatch.setattr(observability, "_get_langfuse_client", Client)
    with pytest.raises(invocation.ToolInvocationError) as caught:
        invocation.invoke(tool)
    assert caught.value.cause is original
    assert seen == [original]


def test_cli_success_survives_flush_failure(monkeypatch, capsys):
    class Client:
        def flush(self):
            raise RuntimeError("flush failure")

    def example():
        """Return a successful result."""
        return "ok"

    monkeypatch.setattr(cli.shared_tools, "TOOLS", (example,))
    monkeypatch.setattr(cli, "invoke", lambda *args, **kwargs: "ok")
    monkeypatch.setattr(observability, "_get_langfuse_client", Client)
    assert cli.main(["example"]) == 0
    assert capsys.readouterr().out.strip() == '"ok"'


@pytest.mark.parametrize("phase", ["extract", "detach"])
def test_trace_context_failure_preserves_dispatch(monkeypatch, phase):
    class Context:
        @staticmethod
        def attach(value):
            return "token"

        @staticmethod
        def detach(token):
            if phase == "detach":
                raise RuntimeError("detach failed")

    class Propagate:
        @staticmethod
        def extract(carrier):
            if phase == "extract":
                raise RuntimeError("extract failed")
            return carrier

    monkeypatch.setattr(observability, "langfuse_enabled", lambda: True)
    monkeypatch.setattr(
        observability.importlib, "import_module",
        lambda name: Context if name.endswith("context") else Propagate,
    )
    calls = []
    with observability.use_incoming_trace_context({"traceparent": "parent"}):
        calls.append(1)
    assert calls == [1]
    assert not observability.trace_context_was_propagated()


def test_base_invocation_never_imports_langfuse():
    script = '''
import importlib.abc
import os
import sys
class RejectLangfuse(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "langfuse" or fullname.startswith("langfuse."):
            raise AssertionError("base usage imported Langfuse")
sys.meta_path.insert(0, RejectLangfuse())
os.environ.pop("TCT_LANGFUSE_ENABLED", None)
os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
os.environ.pop("LANGFUSE_SECRET_KEY", None)
import TCT
from TCT.interfaces.invocation import invoke
def example():
    return 42
assert invoke(example) == 42
assert "langfuse" not in sys.modules
'''
    subprocess.run([sys.executable, "-c", script], check=True)
