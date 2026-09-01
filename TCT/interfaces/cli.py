"""Generate the TCT command-line interface from the shared tool surface."""

from __future__ import annotations

import argparse
import inspect
import json
import types
from collections.abc import Callable
from typing import Any, Union, get_args, get_origin, get_type_hints

from . import tools as shared_tools


class _StringOrListAction(argparse.Action):
    """Return one CLI value as a string and multiple values as a list."""

    def __call__(self, parser, namespace, values, option_string=None):
        value = values[0] if len(values) == 1 else values
        setattr(namespace, self.dest, value)


class _HelpFormatter(
    argparse.ArgumentDefaultsHelpFormatter,
    argparse.RawDescriptionHelpFormatter,
):
    """Preserve shared docs while showing defaults derived from signatures."""


def _command_name(tool: Callable[..., Any]) -> str:
    return tool.__name__.replace("_", "-")


def _parameter_docs(tool: Callable[..., Any]) -> dict[str, str]:
    """Extract Google-style argument descriptions from a tool docstring."""
    lines = (inspect.getdoc(tool) or "").splitlines()
    descriptions: dict[str, list[str]] = {}
    current_name: str | None = None
    in_args = False

    for line in lines:
        stripped = line.strip()
        if stripped == "Args:":
            in_args = True
            continue
        if in_args and stripped.endswith(":") and not line.startswith(" "):
            break
        if not in_args:
            continue

        indentation = len(line) - len(line.lstrip())
        if indentation == 4 and ":" in stripped:
            name, description = stripped.split(":", maxsplit=1)
            current_name = name.strip()
            descriptions[current_name] = [description.strip()]
        elif indentation > 4 and current_name and stripped:
            descriptions[current_name].append(stripped)

    return {name: " ".join(parts) for name, parts in descriptions.items()}


def _json_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise argparse.ArgumentTypeError(f"expected JSON: {error.msg}") from error


def _json_object(value: str) -> dict[str, Any]:
    parsed = _json_value(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("expected a JSON object")
    return parsed


def _non_none_union_args(annotation: Any) -> tuple[Any, ...]:
    if get_origin(annotation) not in (Union, types.UnionType):
        return ()
    return tuple(item for item in get_args(annotation) if item is not type(None))


def _argument_options(annotation: Any) -> dict[str, Any]:
    """Translate a Python annotation into argparse keyword arguments."""
    union_args = _non_none_union_args(annotation)
    effective = union_args[0] if len(union_args) == 1 else annotation
    origin = get_origin(effective)
    args = get_args(effective)

    if annotation is Any:
        return {"type": _json_value, "metavar": "JSON"}
    if effective in (str, int, float):
        return {"type": effective}
    if effective is bool:
        return {"action": argparse.BooleanOptionalAction}
    if origin is list:
        item_type = args[0] if args and args[0] in (str, int, float) else str
        return {"type": item_type, "nargs": "+"}
    if origin is dict:
        return {"type": _json_object, "metavar": "JSON"}

    if set(union_args) == {str, list[str]}:
        return {"action": _StringOrListAction, "nargs": "+"}

    return {"type": _json_value, "metavar": "JSON"}


def _add_tool_parser(
    subparsers: argparse._SubParsersAction,
    tool: Callable[..., Any],
) -> None:
    docstring = inspect.getdoc(tool) or ""
    summary = docstring.splitlines()[0] if docstring else tool.__name__
    parser = subparsers.add_parser(
        _command_name(tool),
        help=summary,
        description=docstring,
        formatter_class=_HelpFormatter,
    )
    parameter_docs = _parameter_docs(tool)
    type_hints = get_type_hints(tool)

    for parameter in inspect.signature(tool).parameters.values():
        option = f"--{parameter.name.replace('_', '-')}"
        annotation = type_hints.get(parameter.name, parameter.annotation)
        options = _argument_options(annotation)
        options["dest"] = parameter.name
        options["help"] = parameter_docs.get(parameter.name)

        if parameter.default is inspect.Parameter.empty:
            options["required"] = True
        else:
            options["default"] = parameter.default

        parser.add_argument(option, **options)

    parser.set_defaults(_tool=tool)


def build_parser() -> argparse.ArgumentParser:
    """Build a CLI parser by introspecting the current shared tool registry."""
    parser = argparse.ArgumentParser(
        prog="tct",
        description="Translator Component Toolkit command-line interface.",
        epilog=(
            "Explore commands:\n"
            "  tct --help\n"
            "  tct COMMAND --help\n\n"
            "List options accept one or more space-separated values. "
            "Structured options accept JSON."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    for tool in shared_tools.TOOLS:
        _add_tool_parser(subparsers, tool)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run a shared TCT tool from command-line arguments."""
    namespace = build_parser().parse_args(argv)
    values = vars(namespace)
    tool = values.pop("_tool")
    values.pop("command")
    result = tool(**values)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
