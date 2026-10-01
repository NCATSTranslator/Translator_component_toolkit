"""Deterministic reduction of captured observations; no live service execution.

Evidence is a set of immutable events. Composition is an explicit, closed recipe.
Call nesting is never interpreted as data lineage.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3

from .interfaces.serialization import to_jsonable

REDUCER_VERSION = 1
MAX_EVENTS = 10000


class EvidenceError(ValueError):
    def __init__(self, message, report=None):
        self.report = report
        super().__init__(message)


def canonical(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def accumulate(*collections):
    """Set union: associative, commutative and idempotent; conflicting IDs fail."""
    events = {}
    identities = {}
    for collection in collections:
        if not isinstance(collection, list):
            raise EvidenceError("events must be a list of execution records")
        for native in collection:
            event = json.loads(canonical(to_jsonable(native)))
            if not isinstance(event, dict) or event.get("format_version") != 1:
                raise EvidenceError("Unsupported execution event format")
            key = digest(event)
            identity = (event.get("run_id"), event.get("call_id"))
            if not all(isinstance(x, str) and x for x in identity):
                raise EvidenceError("Events require run_id and call_id")
            if identity in identities and identities[identity] != key:
                raise EvidenceError(f"Conflicting event identity: {identity}")
            identities[identity] = key
            events[key] = event
            if len(events) > MAX_EVENTS:
                raise EvidenceError("Evidence exceeds 10000 unique events")
    return [events[key] for key in sorted(events)]


def read_run(store, run_id):
    """Read a journal snapshot without creating files or trusting artifact names."""
    root = Path(store).expanduser().resolve()
    database = root / "journal.sqlite3"
    if not database.is_file():
        raise EvidenceError("Execution journal does not exist")
    records = []
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT call_id, step_id, status, event_hash FROM calls WHERE run_id=? ORDER BY step_id",
            (run_id,),
        ).fetchall()
        if not rows:
            raise EvidenceError("Run does not exist or has no recorded calls")
        for call_id, step_id, status, checksum in rows:
            if not checksum:
                records.append(
                    {
                        "format_version": 1,
                        "run_id": run_id,
                        "call_id": call_id,
                        "step_id": step_id,
                        "status": status,
                    }
                )
                continue
            if len(checksum) != 64 or any(
                x not in "0123456789abcdef" for x in checksum
            ):
                raise EvidenceError("Invalid artifact digest")
            raw = (root / "artifacts" / checksum).read_bytes()
            if hashlib.sha256(raw).hexdigest() != checksum:
                raise EvidenceError("Execution artifact checksum mismatch")
            record = json.loads(raw)
            if (
                record.get("run_id"),
                record.get("call_id"),
                record.get("step_id"),
                record.get("status"),
            ) != (run_id, call_id, step_id, status):
                raise EvidenceError("Journal index and execution artifact disagree")
            records.append(record)
    finally:
        connection.close()
    return accumulate(records)


def inventory(events):
    sources, issues, workflows = {}, [], {}
    for record in accumulate(events):
        event_id = digest(record)
        if (
            record.get("status") != "succeeded"
            or record.get("capture_error")
            or record.get("observation_errors")
        ):
            issues.append(
                {
                    "event_id": event_id,
                    "status": record.get("status"),
                    "operation": record.get("operation"),
                    "capture_error": record.get("capture_error"),
                }
            )
        observations = list(record.get("observations", []))
        output = record.get("output")
        if (
            isinstance(output, dict)
            and output.get("schema_version") == 1
            and "steps" in output
        ):
            workflows[event_id] = output
            for step_id, step in output["steps"].items():
                if step.get("op") == "query":
                    observations.append(
                        {
                            "kind": "service",
                            "status": "received",
                            "status_code": step.get("transport", {}).get("status_code"),
                            "body_json": step.get("response"),
                            "request": {
                                "url": step.get("inputs", {}).get("url"),
                                "arguments": {
                                    "json": step.get("inputs", {}).get("query")
                                },
                            },
                            "workflow_step": step_id,
                            "eligible": step.get("status") == "succeeded",
                        }
                    )
        for index, observation in enumerate(observations):
            if observation.get("kind") != "service":
                continue
            response = observation.get("body_json")
            request = observation.get("request", {})
            query = request.get("arguments", {}).get("json")
            if observation.get("eligible") is False:
                issues.append(
                    {
                        "event_id": event_id,
                        "observation": index,
                        "status": "workflow_step_failed",
                    }
                )
            if (
                observation.get("status") != "received"
                or observation.get("status_code") != 200
            ):
                issues.append(
                    {
                        "event_id": event_id,
                        "observation": index,
                        "status": observation.get("status"),
                        "status_code": observation.get("status_code"),
                    }
                )
                continue
            if not isinstance(response, dict) or not isinstance(
                response.get("message"), dict
            ):
                if isinstance(query, dict) and "message" in query:
                    issues.append(
                        {
                            "event_id": event_id,
                            "observation": index,
                            "status": "invalid_trapi_body",
                        }
                    )
                continue  # Normalization and discovery are retained events, not KG responses.
            content = {"url": request.get("url"), "query": query, "response": response}
            source_id = "source:" + digest(content)
            source = sources.setdefault(
                source_id, content | {"origins": [], "eligible": False}
            )
            source["eligible"] |= (
                record.get("status") == "succeeded"
                and not record.get("capture_error")
                and not record.get("observation_errors")
                and observation.get("eligible", True)
            )
            source["origins"].append(
                {
                    "event_id": event_id,
                    "observation": index,
                    "call_id": record["call_id"],
                }
            )
    for source in sources.values():
        source["origins"] = sorted(
            {canonical(o): o for o in source["origins"]}.values(), key=canonical
        )
    return sources, sorted(issues, key=canonical), workflows


def _pointer(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise EvidenceError("Selection paths must be JSON pointers")
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _attrs(value, path, additions):
    if "attributes" not in value:
        value["attributes"] = []
        additions.append(path + "/attributes")


def _prepare(source, source_id, mapping, query_graph, version):
    """Normalize structural omissions only; never invent biomedical statements."""
    if not source["eligible"]:
        raise EvidenceError(
            f"{source_id}: source capture did not complete successfully"
        )
    response = deepcopy(source["response"])
    message = response["message"]
    request = source.get("query") or {}
    local = message.get("query_graph") or request.get("message", {}).get("query_graph")
    sent_graph = request.get("message", {}).get("query_graph")
    if (
        message.get("query_graph")
        and sent_graph
        and canonical(local) != canonical(sent_graph)
    ):
        raise EvidenceError(
            "Provider query-graph rewrite requires an explicit conversion"
        )
    if not isinstance(local, dict):
        raise EvidenceError(f"{source_id}: explicit provider query graph is missing")
    node_map, edge_map = mapping.get("nodes", {}), mapping.get("edges", {})
    path_map = mapping.get("paths", {})
    for field, rename in [
        ("nodes", node_map),
        ("edges", edge_map),
        ("paths", path_map),
    ]:
        if set(rename) != set(local.get(field, {})) or len(set(rename.values())) != len(
            rename
        ):
            raise EvidenceError(
                f"{source_id}: {field} mapping must map each local ID once without collapsing IDs"
            )
        if not set(rename.values()) <= set(query_graph.get(field, {})):
            raise EvidenceError(f"{source_id}: unknown target {field} mapping")
    for field, rename in [("edges", edge_map), ("paths", path_map)]:
        for key, target in rename.items():
            item, combined = local[field][key], query_graph[field][target]
            if any(
                node_map.get(item[end]) != combined[end]
                for end in ["subject", "object"]
            ):
                raise EvidenceError(
                    f"{source_id}: mapping changes {field} direction/endpoints"
                )
    if response.get("status") not in (None, "Success", "OK"):
        raise EvidenceError(f"{source_id}: provider reported {response['status']}")
    kg = message.get("knowledge_graph")
    if (
        not isinstance(kg, dict)
        or not isinstance(kg.get("nodes"), dict)
        or not isinstance(kg.get("edges"), dict)
    ):
        raise EvidenceError(f"{source_id}: incomplete knowledge graph")
    additions = []
    if version == "1.5.0":
        if local.get("paths"):
            raise EvidenceError("Path conversion to TRAPI 1.5.0 is unsupported")
        for node_id, node in kg["nodes"].items():
            _attrs(node, f"/knowledge_graph/nodes/{node_id}", additions)
        for aux_id, aux in (message.get("auxiliary_graphs") or {}).items():
            if not isinstance(aux, dict):
                raise EvidenceError(
                    "Legacy list-valued auxiliary graphs require an explicit conversion"
                )
            _attrs(aux, f"/auxiliary_graphs/{aux_id}", additions)
        for i, result in enumerate((message.get("results") or [])):
            for bindings in [
                result.get("node_bindings", {}),
                *(a.get("edge_bindings", {}) for a in result.get("analyses", [])),
            ]:
                for key, values in bindings.items():
                    for j, binding in enumerate(values):
                        _attrs(binding, f"/results/{i}/bindings/{key}/{j}", additions)
    # Full local responses are validated before any remapping.
    from .trapi_validation import validate

    checked = validate(response, version)
    if not checked["valid"]:
        raise EvidenceError(f"{source_id}: invalid source response", checked)
    return message, additions


def _ids(binding, version):
    return [b["id"] for b in binding] if version == "1.5.0" else binding["ids"]


def _bindings(ids, version):
    return (
        [{"id": item, "attributes": []} for item in sorted(set(ids))]
        if version == "1.5.0"
        else {"ids": sorted(set(ids))}
    )


def _rewrite_support(attributes, auxiliary):
    for attr in attributes or []:
        if attr.get("attribute_type_id") == "biolink:support_graphs":
            if not isinstance(attr.get("value"), list):
                raise EvidenceError("support_graphs attribute must contain a list")
            attr["value"] = [auxiliary[x] for x in attr["value"]]
        _rewrite_support(attr.get("attributes", []), auxiliary)


def _merge(mapped, version):
    node_variants = {}
    nodes, edges, auxiliary, source_results, references, variants = (
        {},
        {},
        {},
        {},
        {},
        {},
    )
    for source_id in sorted(mapped):
        message, mapping = mapped[source_id]
        kg = message["knowledge_graph"]
        edge_ids = {key: "edge:" + digest([source_id, key]) for key in kg["edges"]}
        aux_ids = {
            key: "aux:" + digest([source_id, key])
            for key in (message.get("auxiliary_graphs") or {})
        }
        references[source_id] = {"edges": edge_ids, "auxiliary_graphs": aux_ids}
        for node_id, node in kg["nodes"].items():
            node = deepcopy(node)
            _rewrite_support(node.get("attributes", []), aux_ids)
            variants.setdefault(node_id, {})[digest(node)] = node
            node_variants.setdefault(node_id, {})[source_id] = node
        for key, edge in kg["edges"].items():
            value = deepcopy(edge)
            if (
                value["subject"] not in kg["nodes"]
                or value["object"] not in kg["nodes"]
            ):
                raise EvidenceError(f"{source_id}: edge {key} refers to an absent node")
            _rewrite_support(value.get("attributes", []), aux_ids)
            edges[edge_ids[key]] = value
        for key, graph in (message.get("auxiliary_graphs") or {}).items():
            value = deepcopy(graph)
            value["edges"] = [edge_ids[x] for x in value["edges"]]
            _rewrite_support(value.get("attributes", []), aux_ids)
            auxiliary[aux_ids[key]] = value
        results = deepcopy(message.get("results") or [])
        for result in results:
            result["node_bindings"] = {
                mapping["nodes"][key]: value
                for key, value in result["node_bindings"].items()
            }
            for values in result["node_bindings"].values():
                if not set(_ids(values, version)) <= set(kg["nodes"]):
                    raise EvidenceError(
                        f"{source_id}: node binding refers to an absent node"
                    )
                if version == "1.5.0":
                    for binding in values:
                        _rewrite_support(binding.get("attributes", []), aux_ids)
            for analysis in result.get("analyses") or []:
                remapped = {}
                for key, values in analysis.get("edge_bindings", {}).items():
                    if version == "1.5.0":
                        for binding in values:
                            binding["id"] = edge_ids[binding["id"]]
                            _rewrite_support(binding.get("attributes", []), aux_ids)
                        remapped[mapping["edges"][key]] = values
                    else:
                        remapped[mapping["edges"][key]] = {
                            "ids": [edge_ids[x] for x in values["ids"]]
                        }
                if "edge_bindings" in analysis:
                    analysis["edge_bindings"] = remapped
                if "path_bindings" in analysis:
                    analysis["path_bindings"] = {
                        mapping["paths"][k]: {"ids": [aux_ids[x] for x in v["ids"]]}
                        for k, v in analysis["path_bindings"].items()
                    }
                if "support_graphs" in analysis:
                    analysis["support_graphs"] = [
                        aux_ids[x] for x in analysis["support_graphs"]
                    ]
                _rewrite_support(analysis.get("attributes", []), aux_ids)
        source_results[source_id] = results
    for node_id, choices in variants.items():
        values = [choices[k] for k in sorted(choices)]
        node = deepcopy(values[0])
        node["categories"] = sorted({c for v in values for c in v["categories"]})
        attrs = {canonical(a): a for v in values for a in (v.get("attributes") or [])}
        if attrs or version == "1.5.0":
            node["attributes"] = [attrs[k] for k in sorted(attrs)]
        # Node disallows arbitrary properties in 1.5. Preserve variants in the
        # top-level provenance extension, associated with their source IDs.
        nodes[node_id] = node
    return (
        {"nodes": nodes, "edges": edges},
        auxiliary,
        source_results,
        references,
        node_variants,
    )


def _transform(composition, sources):
    from .workflow import run_workflow

    recipe = deepcopy(composition["workflow"])
    for step in recipe.get("steps", []):
        if step.get("op") == "query":
            raise EvidenceError("Evidence replay does not execute network queries")
        if step.get("op") == "source":
            if (
                set(step) != {"id", "op", "source_id"}
                or step["source_id"] not in sources
            ):
                raise EvidenceError(
                    "source steps must reference an explicitly mapped source"
                )
            step.update(
                op="literal", value=deepcopy(sources[step.pop("source_id")]["response"])
            )
    bundle = run_workflow(recipe)
    if bundle["status"] != "succeeded":
        raise EvidenceError("Composition workflow failed", bundle)
    output_name = composition["selection"]["output"]
    rows = bundle["outputs"].get(output_name)
    if not isinstance(rows, list):
        raise EvidenceError("Selected workflow output must be a list of answer rows")
    # Exclude wall-clock metadata from the semantic hash; retain decisions and lineage.
    trace = {
        key: {
            field: value
            for field, value in step.items()
            if field
            in (
                "op",
                "status",
                "inputs",
                "output",
                "row_lineage",
                "decisions",
                "dependencies",
                "depends_on",
            )
        }
        for key, step in bundle["steps"].items()
    }
    return rows, trace


def _select(rows, selection, query_graph, kg, auxiliary, refs, mappings, version):
    results = {}
    if set(selection.get("nodes", {})) != set(query_graph["nodes"]):
        raise EvidenceError("Selection must bind every query node explicitly")
    if set(selection.get("edges", {})) != set(query_graph.get("edges", {})):
        raise EvidenceError("Selection must bind every query edge explicitly")
    if set(selection.get("paths", {})) != set(query_graph.get("paths", {})):
        raise EvidenceError("Selection must bind every query path explicitly")
    for row_index, row in enumerate(rows):
        nodes = {key: _pointer(row, path) for key, path in selection["nodes"].items()}
        for key, node_id in nodes.items():
            if not isinstance(node_id, str) or node_id not in kg["nodes"]:
                raise EvidenceError(
                    f"Selected node {key} is missing from accumulated evidence"
                )
            qnode = query_graph["nodes"][key]
            if qnode.get("ids") and node_id not in qnode["ids"]:
                raise EvidenceError(
                    f"Selected node {key} violates the query identifier restriction"
                )
            if qnode.get("categories") and not set(qnode["categories"]).intersection(
                kg["nodes"][node_id]["categories"]
            ):
                raise EvidenceError(
                    f"Selected node {key} has no exact requested category; ancestor inference is unsupported"
                )
        edge_bindings, path_bindings = {}, {}
        origins = []
        for field, target in [("edges", edge_bindings), ("paths", path_bindings)]:
            for key, spec in selection.get(field, {}).items():
                source_id = spec["source_id"]
                if (
                    source_id not in refs
                    or key not in mappings[source_id].get(field, {}).values()
                ):
                    raise EvidenceError(
                        f"Selection {key} has no corresponding source query mapping"
                    )
                original = _pointer(row, spec["path"])
                identifiers = original if isinstance(original, list) else [original]
                if not identifiers:
                    raise EvidenceError("Empty answer bindings are unsupported")
                table = refs[source_id][
                    "edges" if field == "edges" else "auxiliary_graphs"
                ]
                ids = [table[x] for x in identifiers]
                target[key] = _bindings(ids, version)
                origins.append(
                    {
                        "query_id": key,
                        "source_id": source_id,
                        "original_ids": identifiers,
                    }
                )
                qedge = query_graph[field][key]
                if field == "edges":
                    for edge_id in ids:
                        edge = kg["edges"][edge_id]
                        if (
                            edge["subject"] != nodes[qedge["subject"]]
                            or edge["object"] != nodes[qedge["object"]]
                        ):
                            raise EvidenceError(
                                f"Selected edge {key} violates query direction/endpoints"
                            )
                        if (
                            qedge.get("predicates")
                            and edge["predicate"] not in qedge["predicates"]
                        ):
                            raise EvidenceError(
                                f"Selected edge {key} violates the requested predicate"
                            )
                else:
                    for aux_id in ids:
                        # Directed reachability within each declared supporting graph.
                        frontier = {nodes[qedge["subject"]]}
                        for _ in range(len(auxiliary[aux_id]["edges"]) + 1):
                            frontier |= {
                                kg["edges"][e]["object"]
                                for e in auxiliary[aux_id]["edges"]
                                if kg["edges"][e]["subject"] in frontier
                            }
                        if nodes[qedge["object"]] not in frontier:
                            raise EvidenceError(
                                "Selected path does not connect the requested endpoints"
                            )
        analysis = {"resource_id": selection["resource_id"]}
        if edge_bindings or version == "1.5.0":
            analysis["edge_bindings"] = edge_bindings
        if path_bindings:
            analysis["path_bindings"] = path_bindings
        result = {
            "node_bindings": {
                key: _bindings([value], version) for key, value in nodes.items()
            },
            "analyses": [analysis],
            "x-tct-evidence": sorted(origins, key=canonical),
        }
        result = results.setdefault(
            canonical(result), result | {"x-tct-selection-rows": []}
        )
        result["x-tct-selection-rows"].append(row_index)
    return [results[key] for key in sorted(results)]


def reduce_evidence(events, composition, version="1.5.0"):
    """Return a validated report or an explicit invalid draft; never perform I/O."""
    from .trapi_validation import validate

    sources, issues, _ = inventory(events)
    report = {"reducer_version": REDUCER_VERSION, "status": "invalid", "issues": issues}
    try:
        composition = deepcopy(composition)
        if not isinstance(composition, dict) or set(composition) - {
            "closed",
            "query_graph",
            "sources",
            "workflow",
            "selection",
        }:
            raise EvidenceError(
                "Unknown composition settings; ranking and automatic query reformulation are unsupported"
            )
        selection = composition.get("selection", {})
        if not isinstance(selection, dict) or set(selection) - {
            "output",
            "resource_id",
            "nodes",
            "edges",
            "paths",
        }:
            raise EvidenceError("Unknown selection settings")
        if version not in {"1.5.0", "2.0.0-beta2"}:
            raise EvidenceError(
                "Unsupported target; final TRAPI 2.0.0 is not available in the pinned schemas"
            )
        if composition.get("closed") is not True:
            raise EvidenceError(
                "Final selection/exclusion requires closed=true and a complete explicit source set"
            )
        if any(item.get("status") == "running" for item in issues):
            raise EvidenceError(
                "Cannot finalize while recorded inputs are still running"
            )
        query_graph = deepcopy(composition["query_graph"])
        if version == "1.5.0" and query_graph.get("paths"):
            raise EvidenceError(
                "Path exports require the explicitly prerelease 2.0.0-beta2 target"
            )
        # Refuse constraints the local selector cannot evaluate.
        for node in query_graph["nodes"].values():
            if set(node) - {"ids", "categories"}:
                raise EvidenceError("Unsupported query-node constraint conversion")
        for edge in query_graph.get("edges", {}).values():
            if (
                set(edge) - {"subject", "object", "predicates", "knowledge_type"}
                or edge.get("knowledge_type", "lookup") != "lookup"
            ):
                raise EvidenceError(
                    "Unsupported query-edge constraint/inference conversion"
                )
        for path in query_graph.get("paths", {}).values():
            if set(path) - {"subject", "object"}:
                raise EvidenceError("Constrained path conversion is unsupported")
        mappings = composition["sources"]
        if not isinstance(mappings, dict) or not mappings:
            raise EvidenceError("Composition requires explicit source mappings")
        selected_sources = {}
        mapped, additions = {}, {}
        for source_id, mapping in sorted(mappings.items()):
            if not isinstance(mapping, dict) or set(mapping) - {
                "nodes",
                "edges",
                "paths",
            }:
                raise EvidenceError("Unknown query mapping settings")
            if source_id not in sources:
                raise EvidenceError(f"Missing closed input: {source_id}")
            selected_sources[source_id] = sources[source_id]
            message, added = _prepare(
                sources[source_id], source_id, mapping, query_graph, version
            )
            mapped[source_id] = (message, mapping)
            additions[source_id] = added
        kg, auxiliary, original_results, references, node_variants = _merge(
            mapped, version
        )
        rows, transformations = _transform(composition, selected_sources)
        results = _select(
            rows,
            composition["selection"],
            query_graph,
            kg,
            auxiliary,
            references,
            mappings,
            version,
        )
        response = {
            "schema_version": version,
            "message": {
                "query_graph": query_graph,
                "knowledge_graph": kg,
                "auxiliary_graphs": auxiliary,
                "results": results,
            },
            "x-tct": {
                "reducer_version": REDUCER_VERSION,
                "source_mappings": mappings,
                "source_results": original_results,
                "node_variants": node_variants,
                "structural_additions": additions,
                "selection": composition["selection"],
                "recipe": composition["workflow"],
                "transformations": transformations,
                "coverage": {
                    "scope": "Closed over the explicitly mapped responses only; not exhaustive biomedical coverage.",
                    "unmapped_source_ids": sorted(set(sources) - set(mappings)),
                    "observed_issue_count": len(issues),
                },
            },
        }
        report["draft"] = response
        report["validation"] = validate(response, version)
        if report["validation"]["valid"]:
            report.update(
                status="valid", rollup_hash=digest(response), references=references
            )
    except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        report["error"] = str(error)
        if isinstance(error, EvidenceError) and error.report is not None:
            report["details"] = error.report
    return report


def evidence(request):
    """One operation for inventory, deterministic replay and validated export."""
    allowed = {"action", "events", "store", "run_id", "composition", "version"}
    if not isinstance(request, dict) or set(request) - allowed:
        raise EvidenceError("Unknown evidence request settings")
    action = request.get("action", "inspect")
    if action not in {"inspect", "replay", "export"}:
        raise EvidenceError("action must be inspect, replay or export")
    if "events" in request:
        if "store" in request or "run_id" in request:
            raise EvidenceError("Choose events or a store/run_id, not both")
        events = accumulate(request["events"])
    else:
        if not all(
            isinstance(request.get(k), str) and request[k] for k in ("store", "run_id")
        ):
            raise EvidenceError("Provide events or both store and run_id")
        events = read_run(request["store"], request["run_id"])
    # An export may itself be recorded into the run being read. Its current
    # journal row is not an unfinished provider input to its own composition.
    from .execution import observation_target

    active = observation_target()
    if active and active.get("operation") == "evidence":
        events = [
            e
            for e in events
            if (e["run_id"], e["call_id"]) != (active["run_id"], active["call_id"])
        ]
    sources, issues, workflows = inventory(events)
    if action == "inspect":
        return {
            "event_count": len(events),
            "sources": {
                key: {
                    "url": source["url"],
                    "query_graph": (source.get("query") or {})
                    .get("message", {})
                    .get("query_graph"),
                    "origins": source["origins"],
                    "eligible": source["eligible"],
                    "node_count": len(
                        (
                            source["response"]["message"].get("knowledge_graph") or {}
                        ).get("nodes", {})
                    ),
                    "edge_count": len(
                        (
                            source["response"]["message"].get("knowledge_graph") or {}
                        ).get("edges", {})
                    ),
                }
                for key, source in sorted(sources.items())
            },
            "issues": issues,
            "workflow_events": sorted(workflows),
        }
    report = reduce_evidence(
        events, request["composition"], request.get("version", "1.5.0")
    )
    if action == "replay":
        return report
    if report["status"] != "valid":
        raise EvidenceError(
            "TRAPI export rejected: "
            + canonical(report.get("validation", report.get("error", report))),
            report,
        )
    return report["draft"]
