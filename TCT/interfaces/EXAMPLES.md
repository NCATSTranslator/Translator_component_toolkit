# TCT interface examples

TCT exposes the same curated tool surface through a generated command-line
interface and an MCP server. The underlying Python functions supply the names,
documentation, annotations, defaults, and invocation behavior for both.

Most operations call live Translator services, so their availability and
response time depend on those services and your network connection.

## Install

Install the Python library and CLI:

```bash
pip install TCT
```

Include the MCP server dependencies when connecting an agent or MCP client:

```bash
pip install "TCT[mcp]"
```

From a source checkout, the corresponding setup is:

```bash
uv sync --extra mcp
```

## Discover capabilities

The root help lists every available command with a one-line description:

```bash
tct --help
```

Each command then exposes its complete shared documentation, parameters,
required inputs, types, defaults, and boolean alternatives:

```bash
tct name-lookup --help
tct normalize-nodes --help
tct path-finder --help
```

This two-step pattern is suitable for either a human exploring interactively
or an agent discovering how to construct a command:

1. Run `tct --help` and select a command.
2. Run `tct COMMAND --help` before invoking it.

Command names and options use kebab-case. CLI output is JSON. List options
accept one or more space-separated values, and mapping or otherwise structured
options accept JSON. MCP exposes the corresponding tool names in snake_case.
Successful CLI results are normalized to JSON; tool failures are written to
standard error and return a nonzero exit status without a Python traceback.

## Name resolution

Resolve one biomedical name and return the highest-ranked result:

```bash
tct name-lookup --query aspirin
```

Return all candidate results and include synonyms:

```bash
tct name-lookup \
  --query aspirin \
  --no-return-top-response \
  --return-synonyms
```

Resolve several names in batches:

```bash
tct batch-name-lookup \
  --strings aspirin ibuprofen acetaminophen \
  --size 25
```

Get synonyms for a CURIE:

```bash
tct get-name-synonyms --query CHEBI:15365
```

## Node normalization

A single `--query` value is passed to TCT as a string:

```bash
tct normalize-nodes --query CHEBI:15365
```

Multiple values are passed as a list. Boolean defaults can be reversed with a
`--no-...` option:

```bash
tct normalize-nodes \
  --query CHEBI:15365 CHEBI:6801 \
  --return-equivalent-identifiers \
  --no-conflate
```

## Translator resources and predicates

Load the curated resource bundle used by the finder tools:

```bash
tct get-translator-resources
```

Discover Knowledge Provider information or supported predicates:

```bash
tct get-kp-info
tct get-api-predicates
```

These results can be large. Redirect the JSON output when it is more useful to
inspect it from a file:

```bash
tct get-api-predicates > api-predicates.json
```

## Structured JSON inputs

Dictionary-like parameters are supplied as JSON objects. Shell quoting keeps
the JSON together as one option value:

```bash
tct optimize-query-for-api \
  --query-json '{"message":{"query_graph":{"nodes":{},"edges":{}}}}' \
  --api-name example-kp \
  --api-predicates '{"example-kp":["biolink:treats"]}'
```

Use `tct optimize-query-for-api --help` to inspect the source documentation for
each of these arguments before constructing a larger query.

## Graph finders

Find selected categories of neighbors for one or more CURIEs:

```bash
tct neighborhood-finder \
  --node MONDO:0005148 \
  --neighbor-categories biolink:Gene biolink:ChemicalEntity
```

Find paths between two CURIEs, optionally constraining intermediate node
categories:

```bash
tct path-finder \
  --start MONDO:0005148 \
  --end CHEBI:15365 \
  --intermediate-categories biolink:Gene
```

## Python use of the shared surface

Developers can continue using TCT's public Python APIs. Interface integrations
that specifically need the curated CLI/MCP surface can import its ordinary
callables without installing MCP:

```python
from TCT.interfaces.tools import name_lookup, normalize_nodes

node = name_lookup("aspirin")
normalized = normalize_nodes(["CHEBI:15365", "CHEBI:6801"])
```

The explicit registry is also available for introspection:

```python
import inspect

from TCT.interfaces.tools import TOOLS

for tool in TOOLS:
    print(tool.__name__, inspect.signature(tool))
    print(inspect.getdoc(tool).splitlines()[0])
```

## MCP server

Start the stdio MCP server after installing the `mcp` extra:

```bash
tct-server
```

An MCP client that launches local stdio servers can use:

```json
{
  "mcpServers": {
    "tct": {
      "command": "tct-server"
    }
  }
}
```

For a development checkout whose dependencies were installed with
`uv sync --extra mcp`, configure the client to run the project command:

```json
{
  "mcpServers": {
    "tct": {
      "command": "uv",
      "args": ["run", "tct-server"],
      "cwd": "/absolute/path/to/Translator_component_toolkit"
    }
  }
}
```

MCP clients obtain tool descriptions and JSON input schemas during normal MCP
discovery. They do not need to parse the CLI help. Both views originate from
the same Python annotations and docstrings, so a parameter change is reflected
in both interfaces.

## Existing MCP entry points

The installed command remains:

```bash
tct-server
```

Repository users can still run:

```bash
python main.py
```

Existing Python imports from `TCT.server` also remain compatibility aliases for
the MCP server and its registered tools.

## Observe agent-facing calls with Langfuse

Install observability separately from the core library. Include `mcp` when the
MCP server is needed:

```bash
uv sync --extra langfuse --extra mcp
```

Set the standard Langfuse credentials, then use the same CLI and MCP commands:

```bash
export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export LANGFUSE_BASE_URL=https://cloud.langfuse.com
export LANGFUSE_TRACING_ENVIRONMENT=development
export TCT_LANGFUSE_ENABLED=true

uv run tct normalize-nodes --query CHEBI:15365
uv run tct-server
```

Langfuse remains disabled unless `TCT_LANGFUSE_ENABLED` is explicitly true.
When enabled, every call made through either adapter is represented as a Langfuse `tool`
observation. The observation includes the interface, tool name, bound input
arguments (including defaults), and a JSON-compatible successful result. It
also records stable payload hashes, byte sizes, batching counts, provider
counts, and TRAPI identifier counts where applicable. These metrics expose
exact duplicates, repeated large arguments, and under-batched calls. No
per-tool decorator is needed because both adapters call the same invocation
function.

To run normally without emitting observations while retaining credentials in
the environment:

```bash
TCT_LANGFUSE_ENABLED=false uv run tct name-lookup --query aspirin
```

Direct developer calls such as `TCT.name_lookup(...)` do not cross the
agent-facing invocation boundary and are not traced by this integration.
