# Explainable query workflows (experimental, version 1)

The workflow API records how explicit operations produce an answer: requests,
responses, data dependencies, filter decisions, and row lineage through joins.
It returns both an executable recipe and a self-contained evidence bundle.
Descriptions are caller-supplied intent, not inferred explanations or private
model reasoning. A reproducible graph path is not proof of a biological mechanism.

This is an **opt-in first slice**. Existing finder, CLI, and MCP tools retain
their existing contracts. Their internal calls do not automatically become
workflow steps. There is no hosted dashboard or automatic question-to-recipe
planner in this change. Workflows do not need Langfuse or an MCP installation.

## Python, CLI, and MCP

```python
import json
from pathlib import Path
from TCT import run_workflow, replay_workflow, validate_workflow

# This committed fixture contains synthetic data and makes no network calls.
recipe = json.loads(Path("examples/workflows/offline_pathway.json").read_text())
plan = validate_workflow(recipe)
bundle = run_workflow(plan["workflow"])
Path("evidence.json").write_text(json.dumps(bundle, indent=2))

replayed = replay_workflow(json.loads(Path("evidence.json").read_text()))
assert replayed["outputs"] == bundle["outputs"]
```

The same operations are MCP tools `validate_query_workflow`,
`run_query_workflow`, and `replay_query_workflow`, with structured JSON outputs.
The CLI publishes `validate-query-workflow`, `run-query-workflow`, and
`replay-query-workflow`; `--workflow` and `--bundle` accept JSON objects as in
the other TCT commands. Save the entire returned bundle for replay. A successful
tool/CLI invocation means the bundle was produced: inspect `bundle.status`,
per-step status, and `output_errors` to determine whether the workflow completed.

## Recipe and operations

A recipe has `schema_version: 1`, `steps`, and an `outputs` object mapping
names to references. A step has a unique `id`, an `op`, operation fields,
and optionally a `description`. References have the form
`{"$ref": "earlier_or_later_step", "path": "/message/results"}`. The path
is an RFC 6901 JSON pointer; omit it to use the entire output. Escape `/` in a
key as `~1`, and `~` as `~0`. Arrays use zero-based indices.

References determine the DAG. Forward references are allowed, cycles are not.
Steps execute sequentially in topological order. Independent branches continue
after another branch fails, and dependents of failed steps are explicitly skipped.
There is no dynamic code evaluation, implicit coercion, or automatic join inference.

| Operation | Fields | Behavior |
| --- | --- | --- |
| `literal` | `value` | Retain caller-supplied JSON, explicitly labeled as such; embedded `$ref` keys are data. |
| `query` | `url`, `query`, optional `timeout_seconds` | POST the resolved TRAPI request exactly as specified. |
| `rows` | `input` reference | Convert an object into sorted `{key, value}` rows, preserving links to original keys. |
| `filter` | `input` reference, `conditions` | AND explicit `{path, operator, value}` conditions; record the disposition of every input row. |
| `project` | `input` reference, `fields` | Select named fields using JSON pointers within each row. |
| `pluck` | `input` reference, `path`, optional `unique` | Extract an array of values; optional deduplication retains every contributing row link. |
| `join` | `left`, `right` references, `left_on`, `right_on` | Exact scalar-key inner join; retain both rows and their lineage, and identify unmatched inputs. |

Filters support `eq`, `ne`, `in`, `not_in`, `gt`, `gte`, `lt`, `lte`, and
`exists`. Equality uses canonical JSON (no string/number or boolean/number
coercion). Ordered comparisons require numbers. Missing paths fail conditions
with a recorded reason, except `exists: false`. Missing projection or join
keys fail the step. Joins reject null keys. No hierarchy, conflation, direction
reversal, or biological equivalence is inferred by local operators.

Each transformation records counts and `row_lineage`. For a row at `/2`, its
lineage names input step IDs and JSON pointers; follow these recursively to
the original query response or caller-supplied data. A query's `inputs` records
the resolved request, while `dependencies` and the recipe record where its
parameters came from. Filters additionally record each condition's outcome.

## Feeding a filtered selection into another query

After turning a first response's `/message/knowledge_graph/edges` into `rows`
and filtering them, this pair of steps sends only selected intermediate IDs
to a second provider. Supply a real, explicitly chosen endpoint in place of
the placeholder:

```json
[
  {
    "id": "selected_ids", "op": "pluck",
    "input": {"$ref": "filtered_edges"},
    "path": "/value/object", "unique": true
  },
  {
    "id": "second_query", "op": "query",
    "url": "https://provider.example/query",
    "timeout_seconds": 60,
    "query": {
      "message": {
        "query_graph": {
          "nodes": {
            "n0": {"ids": {"$ref": "selected_ids"}},
            "n1": {"categories": ["biolink:Disease"]}
          },
          "edges": {
            "e0": {"subject": "n0", "object": "n1", "predicates": ["biolink:associated_with"]}
          }
        }
      }
    }
  }
]
```

Empty `ids` fail before dispatch so an empty upstream selection cannot silently
become an unbounded query. This currently makes that branch incomplete; an
explicit empty-branch operator is future work. No predicates are pruned, and
no retries, redirects, or provider discovery occur. The minimal request and
response checks are **not full TRAPI schema or semantic validation**.

Only synchronous HTTP 200 JSON responses with `message.results` and a
`knowledge_graph` containing `nodes` and `edges` objects are accepted. An
optional provider status must be `Success` or `OK`. Other provider statuses,
HTTP errors, asynchronous job responses, malformed data, and timeouts are
recorded as failures, never empty results. Valid zero-result responses succeed
and carry a `result_count` of zero. The response body, parsed response, HTTP
status, endpoint, and selected response headers are retained when available.

TRAPI response `results`, `analyses`, `sources`, `qualifiers`, attributes, and
auxiliary graphs remain in the snapshot. Joining raw knowledge-graph edges
creates candidate graph connections; it does not enforce result bindings or
establish that a provider answered a multi-hop query. For supported answers,
inspect or operate on the returned result bindings and their evidence.

## Replaying and interpreting evidence

`replay_workflow(bundle)` defaults to **snapshot** mode: no remote calls, saved
query evidence, and recomputed local operations. It checks content hashes and
compares recomputed outputs and lineage with the saved run. Provider timestamps
are retained separately from replay timestamps. Hashes detect modification but
are not signatures or proof of source authenticity.

`replay_workflow(bundle, mode="live")` explicitly contacts the same endpoints
again using the same recipe. It recalculates downstream query inputs from the
new upstream results; it is a workflow rerun, not replay of identical HTTP
bodies regardless of inputs. The new bundle links back with `rerun_of`.
Remote services may change data, normalization, or software. The bundle records
TCT/Python/requests versions and an engine format version, but does not pin remote
builds or promise identical biological results. Build identifiers included by
providers remain in the full responses; absent identifiers are not invented.

Limits in version 1 are 100 steps, 10,000 rows per local transformation,
8 MiB of decoded bytes per HTTP response, and a maximum 120-second requests
socket timeout (60 seconds by default; not a whole-workflow deadline). Exceeding
a limit fails explicitly rather than silently truncating evidence. Large bundles
are returned inline, so callers should use bounded queries and persist results.
There is no server-side session store, filesystem access, or arbitrary tool
invocation exposed through the workflow interpreter.

## Next engineering milestones

1. Record name resolution and normalization as explicit versioned operations,
   retaining rejected candidates and selection criteria. Version 1 expects
   resolved identifiers or caller-supplied literal data.
2. Instrument the existing neighborhood/path finder internals using the same
   evidence model, including per-provider failures and actual query rewrites.
3. Add operations over TRAPI result bindings, preserving analysis/support graphs
   while assembling paths; distinguish inference from retrieved assertions.
4. Store large immutable artifacts by reference and expose inspection tools that
   return only the requested steps/rows, keeping MCP context bounded.
5. Attach RIG conformance evidence using explicit contract/build identities.
   Do not turn source-level conformance into an answer-correctness score.
6. Build the user view: choose a returned path, walk backward through filters
   and joins, inspect supporting records, and export the replayable recipe.

### Optional TRAPI observation capture

The experimental `include_trapi` argument and return envelope have been removed.
The six query/finder/workflow wrappers always return native results. Their
introspected CLI/MCP signatures no longer advertise a representation flag.

Python callers can opt into in-memory observations:

```python
from TCT import execution
from TCT.interfaces.tools import run_query_workflow

with execution({"trapi": True}) as observations:
    bundle = run_query_workflow(recipe)
# bundle is unchanged and can be replayed directly.
# observations contains inputs, operation status, and detached representations.
```

Capture is disabled by default. An omitted setting inherits an enclosing context;
explicit false temporarily disables capture. Langfuse is independently enabled
through its existing environment setting and still observes interface invocations.
This context neither writes files nor enables caching. It does not yet provide
CLI/MCP execution configuration, durable replay state, or a validated TRAPI rollup.

Representations retain their prior limitations: provider failures and empty
results may both return None; parallel results contain only merged edges; finder
output is TRAPI-style and unvalidated. Workflow artifacts preserve individual
query requests/responses, not a compiled query for arbitrary joins. Capture
failures after execution are recorded without replacing the native return value.
