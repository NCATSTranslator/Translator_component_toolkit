"""Explicit query composition, row lineage, and portable evidence snapshots.

This opt-in API is independent of tracing and never executes arbitrary Python.
Recipes are JSON DAGs; references carry data between named operations. Remote
TRAPI responses are retained intact instead of being flattened into merged edges.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import math
import platform
import re
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import requests


SCHEMA_VERSION = 1
ENGINE_VERSION = "1"
MAX_STEPS = 100
MAX_ROWS = 10000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_OPERATIONS = {
    "literal": ({"value"}, set()),
    "query": ({"url", "query"}, {"timeout_seconds"}),
    "rows": ({"input"}, set()),
    "filter": ({"input", "conditions"}, set()),
    "project": ({"input", "fields"}, set()),
    "pluck": ({"input", "path"}, {"unique"}),
    "join": ({"left", "right", "left_on", "right_on"}, set()),
}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pointer_tokens(path: str) -> list[str]:
    if not isinstance(path, str) or (path and not path.startswith("/")):
        raise ValueError("paths must be JSON pointers: empty or beginning with '/'")
    if re.search(r"~(?![01])", path):
        raise ValueError("invalid JSON pointer escape")
    return [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]


class _MissingPath(ValueError):
    pass


def _at(value: Any, path: str) -> Any:
    for token in _pointer_tokens(path):
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
            index = int(token)
            if index >= len(value):
                raise _MissingPath(f"missing path {path!r}")
            value = value[index]
        else:
            raise _MissingPath(f"missing path {path!r}")
    return value


def _references(value: Any) -> list[dict[str, str]]:
    if isinstance(value, dict):
        if "$ref" in value:
            if set(value) - {"$ref", "path"} or not isinstance(value["$ref"], str):
                raise ValueError(
                    "references contain only a string $ref and optional path"
                )
            _pointer_tokens(value.get("path", ""))
            return [value]
        return [ref for item in value.values() for ref in _references(item)]
    if isinstance(value, list):
        return [ref for item in value for ref in _references(item)]
    return []


def _require_reference(value: Any) -> None:
    if not isinstance(value, dict) or "$ref" not in value:
        raise ValueError("transformation inputs must be step references")
    _references(value)


def validate_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a version-1 recipe without making network calls.

    References may point forward in the recipe; execution is topologically sorted.
    Unknown fields, cycles, unknown steps, and unsupported operations are rejected.
    Dynamic input types and paths are checked when their upstream results exist.
    """
    # Strict JSON round-trip also isolates execution from caller-owned objects.
    recipe = json.loads(_json(workflow))
    if not isinstance(recipe, dict) or set(recipe) - {
        "schema_version",
        "steps",
        "outputs",
        "description",
    }:
        raise ValueError(
            "workflow must contain schema_version, steps, outputs, and optional description"
        )
    if (
        type(recipe.get("schema_version")) is not int
        or recipe["schema_version"] != SCHEMA_VERSION
    ):
        raise ValueError("unsupported workflow schema_version")
    if "description" in recipe and not isinstance(recipe["description"], str):
        raise ValueError("workflow description must be a string")
    steps = recipe.get("steps")
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError(f"workflow must have 1..{MAX_STEPS} steps")
    outputs = recipe.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        raise ValueError(
            "workflow outputs must be a nonempty mapping of names to references"
        )
    for output in outputs.values():
        _require_reference(output)
    dependencies: dict[str, list[str]] = {}
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("each step must be an object")
        step_id = step.get("id")
        if not isinstance(step_id, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]*", step_id
        ):
            raise ValueError(
                "step IDs must start with a letter and contain letters, digits, '_' or '-'"
            )
        if step_id in dependencies:
            raise ValueError(f"duplicate step ID: {step_id}")
        op = step.get("op")
        if not isinstance(op, str) or op not in _OPERATIONS:
            raise ValueError(f"unsupported operation: {op}")
        required, optional = _OPERATIONS[op]
        if required - step.keys() or step.keys() - required - optional - {
            "id",
            "op",
            "description",
        }:
            raise ValueError(f"invalid fields for {op} step {step_id}")
        if "description" in step and not isinstance(step["description"], str):
            raise ValueError(
                "step descriptions must be strings (caller-supplied intent)"
            )
        for field in ("input", "left", "right"):
            if field in step:
                _require_reference(step[field])
        if op == "query":
            url = step["url"]
            if not isinstance(url, str):
                raise ValueError("query url must be an explicit HTTP(S) endpoint")
            parsed = urlsplit(url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise ValueError(
                    "query url must be HTTP(S), without credentials or fragment"
                )
            timeout = step.setdefault("timeout_seconds", 60)
            if (
                type(timeout) not in (int, float)
                or not math.isfinite(timeout)
                or not 0 < timeout <= 120
            ):
                raise ValueError("timeout_seconds must be a number in (0, 120]")
            if not isinstance(step["query"], dict):
                raise ValueError("query must be a JSON object")
        if op == "filter":
            conditions = step["conditions"]
            if not isinstance(conditions, list) or not conditions:
                raise ValueError(
                    "filter conditions must be a nonempty list (combined with AND)"
                )
            for condition in conditions:
                if not isinstance(condition, dict) or set(condition) != {
                    "path",
                    "operator",
                    "value",
                }:
                    raise ValueError(
                        "each condition requires path, operator, and value"
                    )
                _pointer_tokens(condition["path"])
                operator = condition["operator"]
                if operator not in (
                    "eq",
                    "ne",
                    "in",
                    "not_in",
                    "gt",
                    "gte",
                    "lt",
                    "lte",
                    "exists",
                ):
                    raise ValueError(f"unsupported filter operator: {operator}")
                if operator in ("in", "not_in") and not isinstance(
                    condition["value"], list
                ):
                    raise ValueError("in/not_in conditions require a list value")
                if operator == "exists" and type(condition["value"]) is not bool:
                    raise ValueError("exists conditions require a boolean value")
                if operator in ("gt", "gte", "lt", "lte") and type(
                    condition["value"]
                ) not in (int, float):
                    raise ValueError("ordered conditions require a numeric value")
        if op == "project":
            if not isinstance(step["fields"], dict) or not step["fields"]:
                raise ValueError(
                    "project fields must map output names to JSON pointers"
                )
            for path in step["fields"].values():
                _pointer_tokens(path)
        for field in ("path", "left_on", "right_on"):
            if field in step:
                _pointer_tokens(step[field])
        if op == "pluck":
            if type(step.setdefault("unique", False)) is not bool:
                raise ValueError("pluck unique must be boolean")
        refs = [] if op == "literal" else _references(step)
        dependencies[step_id] = sorted({ref["$ref"] for ref in refs})
    all_refs = [ref["$ref"] for ref in _references(outputs)]
    all_refs += [ref for refs in dependencies.values() for ref in refs]
    unknown = set(all_refs) - dependencies.keys()
    if unknown:
        raise ValueError(f"unknown step references: {sorted(unknown)}")
    order: list[str] = []
    pending = list(dependencies)
    while pending:
        ready = [key for key in pending if set(dependencies[key]) <= set(order)]
        if not ready:
            raise ValueError("workflow contains a dependency cycle")
        order.extend(ready)
        pending = [key for key in pending if key not in ready]
    return {"workflow": recipe, "execution_order": order, "dependencies": dependencies}


def _resolve(value: Any, records: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        if "$ref" in value:
            return deepcopy(
                _at(records[value["$ref"]]["output"], value.get("path", ""))
            )
        return {key: _resolve(item, records) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, records) for item in value]
    return value


def _link(ref: dict[str, str], key: Any = None) -> dict[str, str]:
    path = ref.get("path", "")
    if key is not None:
        path += "/" + str(key).replace("~", "~0").replace("/", "~1")
    return {"step": ref["$ref"], "path": path}


def _rows(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("operation requires an array; use rows to expand an object")
    if len(value) > MAX_ROWS:
        raise ValueError(f"row limit exceeded ({MAX_ROWS}); narrow the query")
    return value


def _condition(row: Any, condition: dict[str, Any]) -> tuple[bool, str]:
    operator, expected = condition["operator"], condition["value"]
    try:
        actual = _at(row, condition["path"])
    except _MissingPath:
        return (operator == "exists" and expected is False, "missing_path")
    if operator == "exists":
        return expected, "path_present"
    if operator in ("eq", "ne"):
        equal = _json(actual) == _json(expected)
        return (equal if operator == "eq" else not equal), "value_comparison"
    if operator in ("in", "not_in"):
        member = any(_json(actual) == _json(item) for item in expected)
        return (member if operator == "in" else not member), "membership"
    if type(actual) not in (int, float):
        return False, "not_numeric"
    comparison = {
        "gt": actual > expected,
        "gte": actual >= expected,
        "lt": actual < expected,
        "lte": actual <= expected,
    }
    return comparison[operator], "numeric_comparison"


def _transform(
    step: dict[str, Any], args: dict[str, Any]
) -> tuple[Any, dict[str, Any]]:
    op = step["op"]
    if op == "literal":
        return args["value"], {"origin": "caller_supplied"}
    lineage: list[dict[str, Any]] = []
    details: dict[str, Any] = {"row_lineage": lineage}
    output: list[Any] = []

    def emit(value: Any, links: list[dict[str, str]]) -> None:
        if len(output) >= MAX_ROWS:
            raise ValueError(f"row limit exceeded ({MAX_ROWS}); narrow the query")
        lineage.append({"output_path": f"/{len(output)}", "inputs": links})
        output.append(value)

    if op == "rows":
        source = args["input"]
        if not isinstance(source, dict):
            raise ValueError("rows requires an object keyed by record ID")
        for key in sorted(source):
            emit({"key": key, "value": source[key]}, [_link(step["input"], key)])
        details["input_count"] = len(source)
    elif op == "join":
        left, right = _rows(args["left"]), _rows(args["right"])
        index: dict[str, list[int]] = {}

        def join_key(row: Any, path: str) -> str:
            value = _at(row, path)
            if value is None or isinstance(value, (dict, list)):
                raise ValueError("join keys must be non-null JSON scalars")
            return _json(value)

        for j, row in enumerate(right):
            index.setdefault(join_key(row, args["right_on"]), []).append(j)
        matched_left, matched_right = set(), set()
        for i, row in enumerate(left):
            for j in index.get(join_key(row, args["left_on"]), []):
                emit(
                    {"left": row, "right": right[j]},
                    [_link(step["left"], i), _link(step["right"], j)],
                )
                matched_left.add(i)
                matched_right.add(j)
        details.update(
            left_count=len(left),
            right_count=len(right),
            unmatched_left=[i for i in range(len(left)) if i not in matched_left],
            unmatched_right=[i for i in range(len(right)) if i not in matched_right],
            join_type="inner",
            equality="exact_json",
        )
    else:
        source = _rows(args["input"])
        details["input_count"] = len(source)
        decisions = []
        unique: dict[str, int] = {}
        for i, row in enumerate(source):
            links = [_link(step["input"], i)]
            if op == "filter":
                checks = [
                    _condition(row, condition) for condition in args["conditions"]
                ]
                keep = all(passed for passed, _ in checks)
                decisions.append(
                    {
                        "input": links[0],
                        "kept": keep,
                        "conditions": [
                            {"index": j, "passed": passed, "basis": basis}
                            for j, (passed, basis) in enumerate(checks)
                        ],
                    }
                )
                if keep:
                    emit(row, links)
            elif op == "project":
                emit(
                    {name: _at(row, path) for name, path in args["fields"].items()},
                    links,
                )
            elif op == "pluck":
                value = _at(row, args["path"])
                key = _json(value)
                if args["unique"] and key in unique:
                    lineage[unique[key]]["inputs"].extend(links)
                else:
                    unique[key] = len(output)
                    emit(value, links)
        if op == "filter":
            details.update(decisions=decisions, removed_count=len(source) - len(output))
        if op == "pluck":
            details["duplicates_removed"] = len(source) - len(output)
    details["output_count"] = len(output)
    return output, details


def _check_query(query: Any) -> None:
    if not isinstance(query, dict):
        raise ValueError("resolved query must be an object")
    message = query.get("message")
    if not isinstance(message, dict) or not isinstance(
        message.get("query_graph"), dict
    ):
        raise ValueError("query requires a message.query_graph object")
    graph = message["query_graph"]
    nodes, edges = graph.get("nodes"), graph.get("edges")
    if (
        not isinstance(nodes, dict)
        or not nodes
        or not isinstance(edges, dict)
        or not edges
    ):
        raise ValueError(
            "query requires a nonempty message.query_graph with nodes and edges"
        )
    for node in nodes.values():
        if not isinstance(node, dict):
            raise ValueError("query nodes must be objects")
        if "ids" in node and (
            not isinstance(node["ids"], list)
            or not node["ids"]
            or any(
                not isinstance(value, str) or not value.strip() for value in node["ids"]
            )
        ):
            raise ValueError(
                "empty or invalid query IDs; refusing to broaden an empty upstream selection"
            )
    for edge in edges.values():
        if (
            not isinstance(edge, dict)
            or edge.get("subject") not in nodes
            or edge.get("object") not in nodes
        ):
            raise ValueError("query edge endpoints must reference query nodes")


def _query(args: dict[str, Any], record: dict[str, Any]) -> Any:
    _check_query(args["query"])
    # No predicate pruning, retry, redirect, or implicit provider discovery.
    with requests.post(
        args["url"],
        json=args["query"],
        timeout=args["timeout_seconds"],
        allow_redirects=False,
        stream=True,
    ) as response:
        record["evidence_origin"] = "provider_response"
        record["transport"] = {
            "status_code": response.status_code,
            "url": response.url,
            "headers": {
                key: response.headers[key]
                for key in ("Content-Type", "Date")
                if key in response.headers
            },
        }
        chunks = bytearray()
        for chunk in response.iter_content(chunk_size=65536):
            chunks.extend(chunk)
            if len(chunks) > MAX_RESPONSE_BYTES:
                raise ValueError(
                    f"response exceeds {MAX_RESPONSE_BYTES} bytes; no complete snapshot captured"
                )
        body = bytes(chunks).decode("utf-8")
        record["response_text"] = body
        payload = json.loads(body)
        _json(payload)  # Reject non-finite numbers before treating this as evidence.
        record["response"] = payload
        if response.status_code != 200:
            raise ValueError(
                f"provider HTTP {response.status_code}; not an empty result"
            )
        if not isinstance(payload, dict):
            raise ValueError("provider response must be a TRAPI object")
        if payload.get("status") not in (None, "Success", "OK"):
            raise ValueError(
                f"provider status {payload['status']!r}; inspect retained response"
            )
        message = payload.get("message")
        if not isinstance(message, dict) or not isinstance(
            message.get("results"), list
        ):
            raise ValueError("synchronous response requires message.results array")
        kg = message.get("knowledge_graph")
        if (
            not isinstance(kg, dict)
            or not isinstance(kg.get("nodes"), dict)
            or not isinstance(kg.get("edges"), dict)
        ):
            raise ValueError(
                "synchronous response requires knowledge_graph nodes and edges objects"
            )
        record["summary"] = {
            "result_count": len(message["results"]),
            "node_count": len(kg["nodes"]),
            "edge_count": len(kg["edges"]),
        }
        return payload


def _software() -> dict[str, str]:
    try:
        tct_version = version("TCT")
    except PackageNotFoundError:
        tct_version = "uninstalled"
    return {
        "tct": tct_version,
        "python": platform.python_version(),
        "requests": requests.__version__,
    }


def _execute(
    plan: dict[str, Any], saved: dict[str, Any] | None = None
) -> dict[str, Any]:
    recipe = plan["workflow"]
    by_id = {step["id"]: step for step in recipe["steps"]}
    records: dict[str, Any] = {}
    bundle: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "mode": "snapshot" if saved is not None else "live",
        "started_at": _now(),
        "software": _software(),
        "workflow": recipe,
        "workflow_sha256": _hash(recipe),
        "execution_order": plan["execution_order"],
        "steps": records,
    }
    for step_id in plan["execution_order"]:
        step = by_id[step_id]
        dependencies = plan["dependencies"][step_id]
        record: dict[str, Any] = {
            "op": step["op"],
            "dependencies": dependencies,
            "started_at": _now(),
        }
        records[step_id] = record
        started = monotonic()
        blocked = [key for key in dependencies if records[key]["status"] != "succeeded"]
        if blocked:
            record.update(status="skipped", blocked_by=blocked)
        else:
            try:
                parameters = {
                    key: value
                    for key, value in step.items()
                    if key not in {"id", "op", "description"}
                }
                args = (
                    deepcopy(parameters)
                    if step["op"] == "literal"
                    else _resolve(parameters, records)
                )
                record["inputs"] = args
                if step["op"] == "query":
                    if saved is None:
                        output = _query(args, record)
                    else:
                        previous = saved["steps"][step_id]
                        if args != previous.get("inputs"):
                            raise ValueError(
                                "snapshot query inputs differ from recorded request"
                            )
                        for key in (
                            "transport",
                            "response_text",
                            "response",
                            "summary",
                            "error",
                        ):
                            if key in previous:
                                record[key] = deepcopy(previous[key])
                        record["evidence_origin"] = (
                            "saved_response"
                            if "response_text" in previous
                            else "saved_failure"
                        )
                        record["original_started_at"] = previous.get(
                            "original_started_at", previous["started_at"]
                        )
                        if previous["status"] == "failed":
                            record["status"] = "failed"
                        output = deepcopy(previous.get("output"))
                else:
                    output, details = _transform(step, args)
                    record.update(details)
                if record.get("status") != "failed":
                    record.update(
                        status="succeeded", output=output, output_sha256=_hash(output)
                    )
            except (
                ValueError,
                TypeError,
                KeyError,
                requests.RequestException,
            ) as error:
                record.update(
                    status="failed",
                    error={"type": type(error).__name__, "message": str(error)},
                )
        record["duration_seconds"] = monotonic() - started
        record["finished_at"] = _now()
    outputs, output_errors = {}, {}
    for name, ref in recipe["outputs"].items():
        if records[ref["$ref"]]["status"] != "succeeded":
            output_errors[name] = f"step {ref['$ref']} did not succeed"
        else:
            try:
                outputs[name] = _resolve(ref, records)
            except _MissingPath as error:
                output_errors[name] = str(error)
    bundle.update(outputs=outputs, output_errors=output_errors, finished_at=_now())
    bundle["status"] = (
        "succeeded"
        if not output_errors
        and all(r["status"] == "succeeded" for r in records.values())
        else "incomplete"
    )
    if saved is not None:
        bundle["replayed_from"] = saved["bundle_sha256"]
        # Replay recomputes transformations; it must agree with saved evidence.
        for step_id, record in records.items():
            for field in ("status", "inputs", "output", "row_lineage", "decisions"):
                if record.get(field) != saved["steps"][step_id].get(field):
                    raise ValueError(f"snapshot replay differs at {step_id}.{field}")
    bundle["bundle_sha256"] = _hash(bundle)
    return bundle


def run_workflow(workflow: dict[str, Any]) -> dict[str, Any]:
    """Execute a validated recipe and return a self-contained evidence bundle.

    Step failures are retained and their dependents skipped; independent branches
    continue. ``status=incomplete`` must never be interpreted as no evidence found.
    Existing TCT helpers and return shapes are unaffected by this opt-in API.
    """
    return _execute(validate_workflow(workflow))


def replay_workflow(bundle: dict[str, Any], mode: str = "snapshot") -> dict[str, Any]:
    """Replay offline by default, or explicitly rerun remote queries with live.

    Hashes detect accidental modification, not authenticity. Offline replay uses
    saved query responses and recomputes local transformations. Live replay fixes
    the recipe and endpoints, but cannot pin remote data or guarantee equal output.
    """
    if mode not in {"snapshot", "live"}:
        raise ValueError("mode must be snapshot or live")
    snapshot = json.loads(_json(bundle))
    if not isinstance(snapshot, dict):
        raise ValueError("evidence bundle must be a JSON object")
    digest = snapshot.pop("bundle_sha256", None)
    if digest != _hash(snapshot):
        raise ValueError("evidence bundle checksum mismatch")
    snapshot["bundle_sha256"] = digest
    if (
        snapshot.get("schema_version") != SCHEMA_VERSION
        or snapshot.get("engine_version") != ENGINE_VERSION
    ):
        raise ValueError("unsupported evidence bundle or engine version")
    plan = validate_workflow(snapshot["workflow"])
    if snapshot.get("workflow_sha256") != _hash(plan["workflow"]):
        raise ValueError("workflow checksum mismatch")
    if set(snapshot.get("steps", {})) != set(plan["execution_order"]):
        raise ValueError("snapshot step set differs from recipe")
    if mode == "snapshot":
        return _execute(plan, saved=snapshot)
    result = _execute(plan)
    result.pop("bundle_sha256")
    result["rerun_of"] = digest
    result["bundle_sha256"] = _hash(result)
    return result
