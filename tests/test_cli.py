"""Tests for the introspection-generated TCT command-line interface."""

import argparse
import json
from pathlib import Path

import pytest

from TCT.interfaces import cli, tools


def test_cli_exposes_every_shared_tool_as_a_kebab_case_command():
    """The CLI command set comes directly from the curated registry."""
    parser = cli.build_parser()
    subparsers = next(
        action
        for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    )

    assert list(subparsers.choices) == [
        tool.__name__.replace("_", "-") for tool in tools.TOOLS
    ]


def test_cli_help_uses_shared_tool_and_parameter_docs(capsys):
    """Command help is generated from the shared callable docstring."""
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args(["name-lookup", "--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "Resolve a biomedical name or term" in help_text
    assert "Name or term to resolve." in help_text
    assert "--return-top-response | --no-return-top-response" in help_text
    assert "(default: True)" in help_text


def test_root_help_explains_how_to_explore_commands(capsys):
    """Humans and agents can discover the next help command from root help."""
    with pytest.raises(SystemExit) as exit_info:
        cli.build_parser().parse_args(["--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    assert "tct COMMAND --help" in help_text
    assert "Structured options accept JSON." in help_text


def test_cli_parses_unions_lists_booleans_and_defaults():
    """Annotations and defaults determine command-line value conversion."""
    parser = cli.build_parser()

    single = parser.parse_args(["normalize-nodes", "--query", "CHEBI:15365"])
    assert single.query == "CHEBI:15365"
    assert single.conflate is True
    assert single.return_equivalent_identifiers is False

    multiple = parser.parse_args(
        [
            "normalize-nodes",
            "--query",
            "CHEBI:15365",
            "CHEBI:6801",
            "--no-conflate",
            "--return-equivalent-identifiers",
        ]
    )
    assert multiple.query == ["CHEBI:15365", "CHEBI:6801"]
    assert multiple.conflate is False
    assert multiple.return_equivalent_identifiers is True


def test_cli_parses_structured_values_as_json():
    """Mapping annotations accept JSON objects without per-tool parsing code."""
    namespace = cli.build_parser().parse_args(
        [
            "optimize-query-for-api",
            "--query-json",
            '{"message": {"query_graph": {}}}',
            "--api-name",
            "example",
            "--api-predicates",
            '{"example": ["biolink:treats"]}',
        ]
    )

    assert namespace.query_json == {"message": {"query_graph": {}}}
    assert namespace.api_predicates == {"example": ["biolink:treats"]}


def test_cli_invokes_registry_callable_and_prints_json(monkeypatch, capsys):
    """The generated adapter calls the selected shared function by keyword."""

    def echo(message: str, repeat: int = 1) -> dict[str, list[str]]:
        """Echo a message.

        Args:
            message: Text to echo.
            repeat: Number of copies.

        Returns:
            The repeated messages.
        """
        return {"messages": [message] * repeat}

    monkeypatch.setattr(tools, "TOOLS", (echo,))

    assert cli.main(["echo", "--message", "hello", "--repeat", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == {"messages": ["hello", "hello"]}


def test_cli_reports_tool_failures_without_a_traceback(monkeypatch, capsys):
    """Invocation failures become concise CLI errors and a nonzero result."""

    def fail(query: str) -> None:
        """Fail a query.

        Args:
            query: Query that will fail.
        """
        raise ValueError(f"cannot resolve {query}")

    monkeypatch.setattr(tools, "TOOLS", (fail,))

    assert cli.main(["fail", "--query", "unknown"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "tct: fail: cannot resolve unknown\n"


def test_cli_reports_serialization_failures_without_a_traceback(monkeypatch, capsys):
    """Bad result conversion is also a concise nonzero CLI outcome."""

    class InvalidResult:
        def to_dict(self):
            raise ValueError("invalid result")

    def invalid_result() -> object:
        """Return an invalid result."""
        return InvalidResult()

    monkeypatch.setattr(tools, "TOOLS", (invalid_result,))

    assert cli.main(["invalid-result"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "tct: invalid-result: could not serialize result: invalid result\n"
    )