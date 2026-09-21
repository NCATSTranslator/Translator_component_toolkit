"""Tests for shared interface invocation and result serialization."""

import json
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import pytest

from TCT.interfaces.invocation import (
    ResultSerializationError,
    ToolInvocationError,
    dumps_result,
    invoke,
    to_jsonable,
)
from TCT.translator_node import TranslatorNode


def test_invoke_forwards_arguments_and_returns_the_raw_value():
    """The shared boundary does not alter successful library calls."""

    def combine(left: str, right: str = "b") -> tuple[str, str]:
        return left, right

    assert invoke(combine, "a", right="c") == ("a", "c")


def test_invoke_wraps_ordinary_errors_with_tool_context():
    """Adapters receive one stable error type with the original cause."""
    cause = ValueError("invalid input")

    def fail() -> None:
        raise cause

    with pytest.raises(ToolInvocationError) as error:
        invoke(fail)

    assert error.value.tool_name == "fail"
    assert error.value.cause is cause
    assert str(error.value) == "invalid input"
    assert error.value.__cause__ is cause


def test_invoke_does_not_double_wrap_normalized_errors():
    """Nested invocation boundaries preserve the first tool context."""
    original = ToolInvocationError("inner", ValueError("failed"))

    def fail() -> None:
        raise original

    with pytest.raises(ToolInvocationError) as error:
        invoke(fail)

    assert error.value is original


def test_to_jsonable_handles_tct_dataclasses_tables_and_collections():
    """Common TCT result types become nested JSON-compatible values."""

    @dataclass
    class Result:
        node: TranslatorNode
        table: pd.DataFrame
        tags: set[str]

    value = Result(
        node=TranslatorNode(curie="CHEBI:15365", label="aspirin"),
        table=pd.DataFrame([{"score": 0.5}, {"score": float("nan")}]),
        tags={"drug", "chemical"},
    )

    assert to_jsonable(value) == {
        "node": {
            "curie": "CHEBI:15365",
            "label": "aspirin",
            "types": None,
            "synonyms": None,
            "curie_synonyms": None,
            "attributes": None,
            "taxa": None,
        },
        "table": [{"score": 0.5}, {"score": None}],
        "tags": ["chemical", "drug"],
    }


def test_to_jsonable_supports_models_enums_and_to_dict_objects():
    """Interface results can use common model conversion conventions."""

    class Status(Enum):
        READY = "ready"

    class Model:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"status": Status.READY}

    class DictionaryResult:
        def to_dict(self):
            return {"model": Model()}

    assert to_jsonable(DictionaryResult()) == {"model": {"status": "ready"}}


def test_dumps_result_produces_stable_json():
    """CLI serialization is parseable and deterministic."""
    serialized = dumps_result({"z": (2, 1), "a": True})

    assert serialized.index('"a"') < serialized.index('"z"')
    assert json.loads(serialized) == {"a": True, "z": [2, 1]}


def test_dumps_result_normalizes_serialization_errors():
    """Adapters receive a stable error when a custom conversion fails."""
    cause = ValueError("conversion failed")

    class InvalidResult:
        def to_dict(self):
            raise cause

    with pytest.raises(ResultSerializationError) as error:
        dumps_result(InvalidResult())

    assert error.value.cause is cause
    assert error.value.__cause__ is cause
