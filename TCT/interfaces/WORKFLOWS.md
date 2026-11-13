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

1. Promote captured name resolution and normalization into workflow operations
   with explicit references. Version 1 recipes still expect resolved identifiers
   or caller-supplied literal data.
2. Define explicit data dependencies and query-graph mappings for captured
   neighborhood/path finder operations, provider failures and query rewrites.
3. Add operations over TRAPI result bindings, preserving analysis/support graphs
   while assembling paths; distinguish inference from retrieved assertions.
4. Store large immutable artifacts by reference and expose inspection tools that
   return only the requested steps/rows, keeping MCP context bounded.
5. Attach RIG conformance evidence using explicit contract/build identities.
   Do not turn source-level conformance into an answer-correctness score.
6. Build the user view: choose a returned path, walk backward through filters
   and joins, inspect supporting records, and export the replayable recipe.

### Optional execution controls

The experimental `include_trapi` argument and return envelope have been removed.
Functions retain their native results. CLI and MCP adapters each expose one
optional execution setting; ordinary library signatures are unchanged.

```python
from TCT import execution
from TCT.interfaces.tools import run_query_workflow

with execution({"record": True, "store": "./evidence", "trapi": True}) as run:
    bundle = run_query_workflow(recipe)
print(run.run_id)  # Available even when the caller did not choose an ID.
# bundle remains a normal workflow bundle; run is also a list of observations.
```

Use `tct COMMAND ... --execution execution.json` in the CLI, or an `execution`
object alongside normal MCP arguments. An example file/object is:

```json
{
  "record": true,
  "store": "./evidence",
  "run_id": "experiment-001",
  "step_id": "query-001",
  "depends_on": [],
  "trapi": true,
  "langfuse": false
}
```

CLI/MCP durable recording requires a caller-supplied `run_id`, so continuation
never depends on extracting a handle from a changed result payload. Store paths
are local to the machine running TCT. Use a new step_id for each operation; an
omitted step_id is generated. Explicit dependencies must already have succeeded
within the same run. Parent-call links describe nesting, not data dependencies.

`record`, `trapi`, and `langfuse` are independent booleans. Unspecified settings
inherit from the enclosing Python context, and Langfuse otherwise uses the existing
`TCT_LANGFUSE_ENABLED` setting. Explicit false disables the corresponding feature.
A store path alone does not activate recording. Recording requires an explicit
store. Unknown settings and invalid types fail before execution. `cache` is a
fourth independent feature, disabled by default; see Phase 5 below.

With all features disabled, no new persistence, evidence hashing, copying, or SDK
loading occurs. Existing toolkit resource caching is unchanged. Langfuse failures
remain nonfatal. The shared invocation boundary unwraps decorated tools once so
interface calls do not produce duplicate observations. Direct decorated Python
calls use that same instrumentation. All 18 working shared tools and their
resolution, discovery, query, and finder conversion helpers are instrumented.
Other legacy library operations are outside this capture surface. The nineteenth
shared endpoint, `trapi_query_endpoint`, remains explicitly unsupported.

With only `trapi: true`, observations remain in memory. Representations are
unvalidated: native merged provider results still contain only edges, and finder
output is TRAPI-style. Full provider bodies are retained separately in execution
observations. No full rollup is constructed.

Durable recording writes content-addressed JSON observations under `artifacts/`
and indexes calls in `journal.sqlite3`. Artifacts are written atomically and the
SQLite index registers a running call before invocation, then its outcome after.
Duplicate step IDs are rejected before re-execution, including interrupted steps.
This is not automatic retry, caching, or an exactly-once remote execution guarantee.
Inspect an interrupted run before choosing a new step identity. Payload conversion
uses the existing interface serializer; it is not a general Python-object restore
format. Replay reconstruction and schema-validated rollup remain later phases.

A recording failure before invocation reports `operation_completed=False`. A
failure after a successful invocation reports `operation_completed=True`, with
run/call IDs: do not blindly retry. If the tool itself raises and journal finalization
also fails, the original exception is preserved, with a diagnostic note where
supported and a warning/error log. The index may retain a running entry for review.

Thread-pool dispatch uses an explicit copied context for every worker. Context
reset on scope exit prevents settings leaking into unrelated calls. No files or
full responses are sent to Langfuse merely because local recording was enabled;
existing Langfuse input/output capture runs only when tracing is independently on.

### Phase 3 capture coverage

`capture_operation()` uses the same execution boundary as `capture_trapi(kind)`;
it does not add parameters or change native results. Interface adapters unwrap
this boundary once. Nested library operations have their own observations and,
when tracing is enabled, their own spans. Trace counts therefore increase even
though the number of public tool calls and service requests does not.

Each operation records bound inputs before execution, inputs after successful
execution (including legacy mutations), and its native output or exception type.
Buffered service requests retain the requested URL/arguments, HTTP status, exact
body bytes as base64, and decoded JSON when available. Recording reads an already
buffered body; it neither repeats the request nor calls `response.json()` again.
This preserves normalization equivalences and unmatched identifiers, name lookup
candidates and scores, discovery metadata, and full provider envelopes including
nodes, bindings, analyses, qualifiers, sources, and supporting graphs.

Transport exceptions, non-200 responses, malformed JSON, and valid empty results
remain distinguishable in evidence even where a legacy function returns `None`.
Provider merging records inputs, exclusions, and overwritten edge IDs. Query
optimization, provider selection, finder assembly and scoring retain their actual
input/output snapshots; their existing mutations and completion-order behavior
are preserved. A requested recording failure is surfaced instead of being swallowed
as a provider failure by parallel query execution.

Workflow execution and snapshot replay continue to use the existing evidence
bundle, with explicit dependencies, filter decisions and join lineage. The wrapper
captures that bundle without introducing a second streaming-response reader or
changing the workflow's size limits. Elsewhere, parent-call links remain nesting
only: snapshots do not constitute complete data lineage or query-graph mappings.
Deterministic semantic composition and schema validation belong to Phase 4.

Capture starts when enabled. Resource-cache hits record the cached native value;
they cannot recover the original HTTP bodies from a fetch made before capture.
No extra fetch is performed to fill that gap. Missing/incompatible buffered bodies
produce explicit capture diagnostics; durable recording reports a completed-call
capture failure rather than silently claiming complete evidence.

Compatibility fixtures in `tests/test_toolkit_capture.py` cover all 18 working
boundaries across Python, shared invocation, CLI and registered MCP adapters.
Boundary fixtures isolate delegation, return identity, mutations and exceptions;
synthetic service fixtures execute real normalization, lookup, discovery, metadata
updates, query pruning, provider merging, and finder assembly. The nineteenth
endpoint's existing `TypeError` is retained. These fixtures are not biological
goldens, fresh model evaluations, or tests of MCP's stdio transport.

Phase 3 acceptance: 235 offline tests passed, including 71 new capture checks.
The single-NLQ frozen benchmark matched its native-output and final-answer goldens
through Python, CLI and registered MCP. A durable Python run retained 11 operation
records and all four service bodies while issuing the same four requests. Live
service tests, real-agent evaluations, semantic rollup and caching were not run.

### Phase 4: deterministic evidence composition

The new `evidence(request)` tool is shared by Python, CLI and MCP. Existing tool
returns and ordinary execution are unchanged. The registry now has 19 working
operations plus the existing unsupported `trapi_query_endpoint` placeholder.
The request is one JSON object; it does not add a family of CLI flags.

```python
from TCT.interfaces.tools import evidence

source = {"store": "./evidence", "run_id": "experiment-001"}
inventory = evidence(source | {"action": "inspect"})
# Use the returned source IDs and local query graphs to define composition.
report = evidence(source | {"action": "replay", "composition": composition})
response = evidence(source | {"action": "export", "composition": composition})
```

CLI uses `tct evidence --request '<JSON object>'`; MCP uses the same tool with a
`request` object. Alternatively, provide `events` (an execution observation list)
instead of `store`/`run_id`. Inspection lists sources, call/event origins, query
graphs, counts, eligibility and failures. Replay returns the draft, diagnostics,
identifier mappings and semantic rollup hash. Export returns only the validated
TRAPI response, with provenance inside its `x-tct` extension. Invalid exports
raise an error; inspect the replay report for details. None of these operations
contacts a provider. Reading a journal checks its artifact digests and index
identities without creating a missing store. An export may itself be recorded
into the same run; its own pending journal row is excluded from its input set.

A composition object has these fields:

- `closed: true`: the caller declares its explicit source set complete. Referenced
  sources must be present and successfully captured. Other unfinished journal
  calls prevent finalization; failures and unmapped sources remain disclosed.
- `query_graph`: the intended combined query, retaining edge direction and lookup
  semantics. Exact node IDs, categories and predicates are checked for selected
  answers. Biolink ancestor reasoning and inferred edges are not implemented.
- `sources`: map each inspected source ID to `nodes`, `edges`, and optionally
  `paths` dictionaries mapping local query IDs to combined query IDs. Every local
  ID must be mapped once; mappings cannot collapse local IDs or reverse endpoints.
- `workflow`: the existing version-1 DAG recipe. A `source` step with `id` and
  `source_id` supplies a frozen response. `rows`, `filter`, `project`, `pluck` and
  `join` use explicit references and run in dependency order. Network `query`
  steps are forbidden. Other operations, including ranking, are unsupported.
- `selection`: names a workflow `output`, the producing `resource_id`, `nodes`
  (query node to row JSON pointer), and `edges`/`paths` (query ID to
  `{source_id, path}`). Each query element must be explicitly bound. Supply an
  appropriate producer identifier; the synthetic fixture's `infores:tct` is an
  example identifier, not a claim of registration in the InfoRes catalogue.

`tests/fixtures/rollup/composition.json` is a complete example for the original
Alzheimer's NLQ. Its service fixtures and native-output goldens are unchanged
copies from the Phase 1 worktree, with the attachment hash retained in `case.json`.
The recipe uses recorded-source references and the same filters/join. It selects
one chemical → gene → disease answer; all five retrieved edges, including the
three distractors, remain in the accumulated knowledge graph.

Accumulation is set union over canonical JSON event content: duplicate events do
not multiply evidence, and insertion/completion order does not affect the result.
Conflicting content for the same run/call identity is rejected. The semantic hash
excludes capture IDs and workflow timestamps. It includes the explicit recipe,
source mappings, selected answers, retained evidence, filter decisions and row
lineage. This hash identifies a Phase 4 artifact; it is not the execution/cache
identity implemented in Phase 5. Reordering equivalent recipe definitions can still
change this hash; no semantic query equivalences are assumed.

Provider-local edge and auxiliary-graph IDs are deterministically namespaced.
Bindings, supporting-graph references and known support-graph attributes are
rewritten together. CURIE node IDs retain their identity. Conflicting node metadata
has a deterministic display value, combined categories/attributes, and complete
source-specific variants under `x-tct.node_variants`. Provider analyses, scores,
node/edge/path bindings and support graphs survive under `x-tct.source_results`;
they are retained as source evidence, not falsely presented as complete analyses
of the combined query. Selected answers get an explicit composition analysis,
source references and the workflow output row indices that produced them.

Validation uses unmodified, checksum-pinned upstream schemas bundled under
`TCT/schemas`, with OpenAPI 3.0 `nullable` adapted to JSON Schema at load time.
Ordinary exports target TRAPI **1.5.0**. Required empty attribute arrays omitted
by legacy responses are added structurally and listed in `structural_additions`.
No predicates, evidence sources or knowledge-level classifications are invented.
Validation proves structural conformance, with additional reducer reference and
selection checks; it does not establish Biolink conformance or biological truth.

**Version limitation:** the official repository had no final 2.0.0 tag when these
schemas were pinned. Native path exports can explicitly target **2.0.0-beta2**;
output and validation metadata retain that prerelease label. Requesting `2.0.0`
is rejected. Automatic conversion from 1.5.0 or legacy finder path extensions to
2.0 is unsupported, as are constrained paths, unsupported query constraints and
provider query-graph rewrites. External schema references (such as a provider's
workflow extension) that are not vendored produce an explicit validation error;
validation never fetches them. Full response bodies remain in the execution
journal even if no supported rollup can be produced.

The endpoint remains opt-in: capture alone does not automatically compose answers,
select mappings or enable caching.

Phase 4 acceptance: **260 offline tests passed**. The original single-NLQ service
and native-output fixtures produce one validated, traceable TRAPI 1.5.0 answer.
`rollup-golden.json` pins its semantic hash; duplicate events and eight shuffled
completion orders give identical reports. Tests also cover collision remapping,
retained provider analyses/support, dependency order, failed/missing inputs,
journal checksums, same-run recording, schema failures, beta2 native paths and
CLI/MCP/Python output parity. The built wheel includes both pinned schemas,
manifest and license. No live provider or paid model calls were made.

### Phase 5: response caching and execution epochs

The same optional execution setting controls response caching. No additional CLI
flags, MCP tools, or native result envelopes are introduced. `{"cache": true}`
enables **within-run** reuse in memory. `cache: false` explicitly disables it.
Nothing is persisted unless `store` is supplied. For reuse across separate CLI/MCP
calls, supply both `store` and the same `run_id`; these interfaces reject persistent
execution without a run ID. Python can generate an ID in its enclosing context.
Existing resource caching is unchanged, and a resource-cache hit does not imply
that fresh service evidence was observed. Clear that cache explicitly when an
experiment requires a new service trajectory.

Cross-run reuse is opt-in and requires an explicit authorization partition:

```json
{
  "store": "./evidence",
  "run_id": "experiment-002",
  "cache": {
    "scope": "cross_run",
    "mode": "use",
    "authorization_partition": "public-translator-ci",
    "dataset_versions": {"provider-a": "release-2026-09"},
    "epoch": "query-policy-1"
  }
}
```

Only include dataset versions you actually know. These fields declare dependencies;
TCT does not make extra calls to discover versions. All declared dependency versions
participate in identity, so changing an upstream normalizer/provider version, epoch,
authorization partition, runtime environment, endpoint, or effective request causes
a miss. The partition must change when access scope or implicit credentials change.
Explicit credentials also participate in hashing; request bodies and credentials
are not copied into the cache index. Execution recording remains a separate opt-in
feature and retains its existing request observations.

Cross-run lifetimes default to **24 hours for normalization/name resolution, one
hour for capabilities, and 15 minutes for TRAPI**. Override individual durations
with `cache.ttl`, in seconds (for example `{"trapi": 60}`). These are freshness
policies, not guarantees that a live service is deterministic. Unknown service kinds
are never reused across runs. Entries already used by a run stay pinned for that
run; expiry is checked when a new run first looks up a shared entry. Warm hits do
not extend shared expiry. There is no automatic disk eviction in this phase.

Modes are `use`, `refresh`, `bypass`, and `replay`. Refresh issues a new service
request and records a new observation; prior immutable snapshots remain available.
Bypass issues a request without reading or populating reusable entries, but still
records its snapshot when storage is requested. HTTP errors, invalid/non-JSON
responses, reported application errors, and transport failures never populate a
successful cache entry. A failed refresh leaves a previously successful entry intact.
Legacy functions retain their existing return behavior (including `None`); cache
receipts distinguish failure from a successful empty response.

Three hashes serve distinct purposes:

- `original_request_hash` identifies the request before toolkit reformulation.
- `effective_execution_hash` includes the actual service request, its settings,
  dependency versions, auth partition, epoch, and cache/canonicalizer/adapter versions.
- `response_content_hash` identifies the exact response bytes, independent of the request.

Canonicalization sorts JSON object keys only. It preserves arrays, query node IDs,
predicate order, URLs and literal values. Semantic rewrites are not assumed to be
equivalent. The existing provider predicate-pruning operation records
`tct.optimize_query_json.v1` when it changes the original request. Mode, TTL and
telemetry settings do not alter service-response identity. Unsupported non-JSON
request options fail explicitly when caching is requested. Adapter behavior changes
must update the corresponding identity version.

To replay a saved run, use the original cache identity settings with
`"mode": "replay", "snapshot_run": "experiment-002"` and a **different** `run_id`.
Replay performs no service requests. Missing, exhausted or damaged snapshots fail
locally; there is no fallback to live HTTP. Occurrences of the same effective request
are consumed in their recorded order; independent requests can be interleaved.
`replay.sqlite3` stores transactional cursors so continuation works across separate
CLI processes and MCP calls. Use a fresh replay run ID to start again. The source
cache index and artifacts remain unchanged. Transport exception classes can be
replayed; original exception objects, sockets, elapsed timings and prepared-request
objects are not reconstructed. Streaming workflow responses keep their 8 MiB limit;
an incomplete response cannot be replayed as a successful snapshot.

`cache.sqlite3` indexes immutable snapshots in the same content-addressed artifact
store as optional recording. Cache-only execution creates no call journal and
does not enable Langfuse or TRAPI capture. Python exposes receipts as
`run.cache_events`; when capture is enabled, service observations and workflow
steps carry the corresponding receipts. The `evidence` tool continues to export
the validated TRAPI rollup from captured evidence without adding cache envelopes
to ordinary tool results. Requested storage failures surface completed-call status.

Nested cache policy objects inherit their outer fields; supplied fields replace
those fields (including dependency and TTL maps). Explicit false disables caching
until the nested context exits. Workers receive the caller's execution context.
Simultaneous cold misses may issue multiple requests; this is not an exactly-once
HTTP protocol. Replayed calls reserve an occurrence before returning it; a process
crash after reservation requires inspection or a new replay run ID.

This boundary covers the instrumented normalization, discovery, provider and
pathfinder helpers plus workflow queries. Uninstrumented legacy functions, bulk
graph downloads and the unsupported endpoint placeholder are outside its scope.
The separate benchmark worktree labels the same NLQ as cold, warm, refreshed or
replayed. Its warmup is a separate fixed trajectory; it never supplies an agent's
answer or conversation history. Phase 6 comparative evaluation remains a separate
user trigger.

Phase 5 acceptance (2026-10-01): **306 offline regression tests and 33 benchmark
tests passed**. The 46 cache tests cover default isolation, nested policies,
independent capture, explicit CLI/MCP settings, worker propagation, expiration,
dependency/authorization invalidation, canonicalization, refresh/bypass, failures,
checksums, persistent replay cursors and bounded workflow responses. The same
single NLQ retains its native goldens and Phase 4 rollup hash in all four cache
scenarios. The benchmark's fixed trajectory uses 4/0/4/0 evaluation service calls
for cold/warm/refreshed/replayed samples across Python, CLI and registered MCP.
The sampled adapter test allows valid wording variation and retains its budget
and resume controls. No live services, real models or paid providers were used.
