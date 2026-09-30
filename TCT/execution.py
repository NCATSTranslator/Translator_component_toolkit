"""Opt-in, context-local evidence collection without changing operation returns.

This initial collector is in-memory. It is not a durable replay journal or a
TRAPI validator. Langfuse remains independently controlled by its existing flag.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from inspect import signature

from .trapi_representation import represent_trapi


_collector = ContextVar("tct_trapi_collector", default=None)


@contextmanager
def execution(config=None):
    """Collect TRAPI observations with ``execution({"trapi": True})``.

    An omitted setting inherits the enclosing collector; explicit false disables
    it locally. A true setting starts a fresh collection. No files are written.
    """
    config = {} if config is None else config
    if not isinstance(config, dict) or set(config) - {"trapi"}:
        raise ValueError("execution currently accepts only the 'trapi' setting")
    if "trapi" in config and type(config["trapi"]) is not bool:
        raise ValueError("trapi must be a boolean")
    records = _collector.get()
    if "trapi" in config:
        records = [] if config["trapi"] else None
    token = _collector.set(records)
    try:
        yield records
    finally:
        _collector.reset(token)


def capture_trapi(kind):
    """Decorate an operation, emitting evidence separately from its result."""

    def decorate(function):
        contract = signature(function)

        @wraps(function)
        def captured(*args, **kwargs):
            records = _collector.get()
            if records is None:
                return function(*args, **kwargs)
            bound = contract.bind(*args, **kwargs)
            bound.apply_defaults()
            record = {
                "operation": function.__name__,
                "status": "running",
            }
            try:
                record["inputs"] = deepcopy(dict(bound.arguments))
            except Exception as error:
                record["input_capture_error"] = type(error).__name__
            records.append(record)
            try:
                result = function(*args, **kwargs)
            except BaseException as error:
                record.update(status="failed", error_type=type(error).__name__)
                raise
            record["status"] = "succeeded"
            try:
                record["trapi"] = represent_trapi(result, kind)
            except Exception as error:
                # The operation has already completed; never replace its result.
                record["capture_error"] = type(error).__name__
            return result

        return captured

    return decorate
