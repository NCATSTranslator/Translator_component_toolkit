"""Shared opt-in execution context for interface and decorated Python calls."""

from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from copy import deepcopy
from functools import wraps
from inspect import signature
import logging
import os
from uuid import uuid4

from .trapi_representation import represent_trapi

_settings = ContextVar("tct_execution_settings", default=None)
_run = ContextVar("tct_execution_run", default=None)
_active = ContextVar("tct_execution_call", default=None)
_cache = ContextVar("tct_execution_cache", default=None)
logger = logging.getLogger(__name__)


class ExecutionRecordingError(RuntimeError):
    """A requested journal write failed; expose whether the operation completed."""

    def __init__(self, message, *, operation_completed, run_id=None, call_id=None):
        self.operation_completed = operation_completed
        self.run_id = run_id
        self.call_id = call_id
        super().__init__(
            f"{message}; operation_completed={operation_completed}; run_id={run_id}; call_id={call_id}"
        )


class ExecutionRun(list):
    """In-memory observations plus an optional durable run identity."""

    def __init__(self, run_id, journal=None):
        super().__init__()
        self.run_id = run_id
        self.journal = journal
        self.cache_events = []


def langfuse_override():
    return (_settings.get() or {}).get("langfuse")


def execution_metadata():
    active = _active.get()
    return (
        {
            f"tct.execution.{key}": active[key]
            for key in ("run_id", "call_id", "parent_call_id")
        }
        if active
        else {}
    )


def validate_execution(config):
    allowed = {
        "trapi",
        "record",
        "langfuse",
        "store",
        "run_id",
        "step_id",
        "depends_on",
        "cache",
    }
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("Unknown execution settings")
    for key in ("trapi", "record", "langfuse"):
        if key in config and type(config[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    if "cache" in config and config["cache"] is not False:
        from .response_cache import validate_policy

        validate_policy(config["cache"], partial=True)
    for key in ("store", "run_id", "step_id"):
        if key in config and (
            not isinstance(config[key], str) or not config[key].strip()
        ):
            raise ValueError(f"{key} must be a nonempty string")
    if "depends_on" in config and (
        not isinstance(config["depends_on"], list)
        or not all(isinstance(x, str) and x for x in config["depends_on"])
        or len(set(config["depends_on"])) != len(config["depends_on"])
    ):
        raise ValueError("depends_on must contain distinct nonempty step IDs")
    return dict(config) | (
        {"cache": deepcopy(config["cache"])}
        if isinstance(config.get("cache"), dict)
        else {}
    )


def _merge_settings(previous, supplied):
    settings = previous | supplied
    if isinstance(previous.get("cache"), dict) and isinstance(
        supplied.get("cache"), dict
    ):
        settings["cache"] = previous["cache"] | supplied["cache"]
    return settings


@contextmanager
def execution(config=None):
    """Enable independent tracing, TRAPI capture, recording, or response caching.

    Unspecified settings inherit. False explicitly disables a feature. Durable
    recording requires a store; Python can generate a run_id on first activation.
    """
    supplied = validate_execution({} if config is None else config)
    previous = _settings.get() or {}
    settings = _merge_settings(previous, supplied)
    if settings.get("record") and not settings.get("store"):
        raise ValueError("record=true requires an explicit store")
    if settings.get("depends_on") and not settings.get("record"):
        raise ValueError("depends_on requires durable recording")
    cache_enabled = settings.get("cache", False) is not False
    active = bool(settings.get("trapi") or settings.get("record") or cache_enabled)
    run = _run.get() if active else None
    changed_run = any(
        key in supplied and supplied[key] != previous.get(key)
        for key in ("run_id", "store", "record")
    )
    if active and (run is None or changed_run):
        run_id = settings.get("run_id") or uuid4().hex
        journal = None
        if settings.get("record"):
            try:
                from .journal import Journal

                journal = Journal(settings["store"])
            except Exception as error:
                raise ExecutionRecordingError(
                    "Cannot initialize journal",
                    operation_completed=False,
                    run_id=run_id,
                ) from error
        run = ExecutionRun(run_id, journal)
        settings["run_id"] = run_id
    cache = None
    if cache_enabled:
        from .response_cache import CacheSession, validate_policy

        policy = validate_policy(settings["cache"])
        cache = CacheSession(settings, policy, run, previous=_cache.get())
    setting_token = _settings.set(settings)
    run_token = _run.set(run)
    cache_token = _cache.set(cache)
    try:
        yield run
    finally:
        _cache.reset(cache_token)
        _run.reset(run_token)
        _settings.reset(setting_token)


@contextmanager
def interface_execution(config=None):
    supplied = validate_execution({} if config is None else config)
    merged = _merge_settings(_settings.get() or {}, supplied)
    persistent = merged.get("record") or (
        merged.get("cache", False) is not False and merged.get("store")
    )
    if persistent and not merged.get("run_id"):
        raise ValueError("CLI/MCP persistent execution requires an explicit run_id")
    with execution(supplied) as run:
        yield run


def submit_with_context(executor, function, /, *args, **kwargs):
    """Submit with a separate copy of the caller's context for each worker."""
    return executor.submit(copy_context().run, function, *args, **kwargs)


def _finish(run, record, completed):
    if run.journal:
        try:
            run.journal.finish(record)
        except Exception as error:
            raise ExecutionRecordingError(
                "Cannot finalize journal; inspect before retrying",
                operation_completed=completed,
                run_id=run.run_id,
                call_id=record["call_id"],
            ) from error


def execute(function, args, kwargs, *, interface=None, kind=None):
    """One execution boundary shared by interface wrappers and decorators."""
    run = _run.get()
    settings = _settings.get() or {}
    capturing = run is not None and (settings.get("trapi") or settings.get("record"))
    if interface is None and not capturing:
        enabled = settings.get("langfuse")
        if enabled is False or (
            enabled is None
            and os.getenv("TCT_LANGFUSE_ENABLED", "").strip().lower()
            in {"", "0", "false", "no", "off"}
        ):
            return function(*args, **kwargs)
    record = None
    token = None
    if capturing:
        parent = _active.get()
        same_run = parent and parent["run_id"] == run.run_id
        call_id = uuid4().hex
        record = {
            "format_version": 1,
            "run_id": run.run_id,
            "call_id": call_id,
            "step_id": (settings.get("step_id") if not same_run else None) or call_id,
            "parent_call_id": parent["call_id"] if same_run else None,
            "depends_on": list(settings.get("depends_on", [])) if not same_run else [],
            "operation": function.__name__,
            "module": function.__module__,
            "interface": interface or "python",
            "status": "running",
        }
        try:
            bound = signature(function).bind(*args, **kwargs)
            bound.apply_defaults()
            record["inputs"] = deepcopy(dict(bound.arguments))
        except Exception as error:
            record["input_capture_error"] = type(error).__name__
            if run.journal:
                raise ExecutionRecordingError(
                    "Cannot capture inputs before execution",
                    operation_completed=False,
                    run_id=run.run_id,
                    call_id=call_id,
                ) from error
        if run.journal:
            try:
                run.journal.begin(record)
            except Exception as error:
                raise ExecutionRecordingError(
                    str(error),
                    operation_completed=False,
                    run_id=run.run_id,
                    call_id=call_id,
                ) from error
        run.append(record)
        token = _active.set(record)
    elif _active.get() is not None:
        token = _active.set(None)
    try:
        # Interfaces retain their existing tracing path. Decorated direct calls
        # can also trace, but import no SDK when the feature is disabled.
        from .interfaces.telemetry import observe_invocation

        with observe_invocation(function, args, kwargs, interface) as observe_result:
            result = function(*args, **kwargs)
            observe_result(result)
    except BaseException as error:
        if record is not None:
            record.update(status="failed", error_type=type(error).__name__)
            try:
                _finish(run, record, False)
            except ExecutionRecordingError as recording_error:
                if hasattr(error, "add_note"):
                    error.add_note(str(recording_error))
                logger.error("%s", recording_error)
        raise
    else:
        if record is not None:
            record["status"] = "succeeded"
            try:
                record["output"] = deepcopy(result)
                if "inputs" in record:
                    record["inputs_after"] = deepcopy(dict(bound.arguments))
                if record.get("observation_errors"):
                    raise ValueError("Incomplete service observation")
                if kind and settings.get("trapi"):
                    record["trapi"] = represent_trapi(result, kind)
            except Exception as error:
                record["capture_error"] = type(error).__name__
                if run.journal:
                    record["status"] = "capture_failed"
                    _finish(run, record, True)
                    raise ExecutionRecordingError(
                        "Operation succeeded but output capture failed",
                        operation_completed=True,
                        run_id=run.run_id,
                        call_id=record["call_id"],
                    ) from error
            _finish(run, record, True)
        return result
    finally:
        if token is not None:
            _active.reset(token)


def capture_trapi(kind=None):
    """Record separately from the native return; adapters avoid double wrapping."""

    def decorate(function):
        @wraps(function)
        def captured(*args, **kwargs):
            return execute(function, args, kwargs, kind=kind)

        captured.__tct_capture_kind__ = kind
        captured.__tct_capture__ = True
        return captured

    return decorate


# The same boundary also captures operations without a TRAPI result adapter.
capture_operation = capture_trapi


def observation_target():
    """Internal capture sink; disabled execution must not inspect responses."""
    settings = _settings.get() or {}
    return _active.get() if settings.get("trapi") or settings.get("record") else None


def cache_session():
    """Internal HTTP boundary; reading it does not import hashing or persistence."""
    return _cache.get()


def observe_evidence(kind, **data):
    """Attach explicitly supplied evidence; never infer dependencies from nesting."""
    target = observation_target()
    if target is not None:
        try:
            target.setdefault("observations", []).append(
                {"kind": kind, **deepcopy(data)}
            )
        except Exception as error:
            target.setdefault("observation_errors", []).append(type(error).__name__)
