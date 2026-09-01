# Langfuse observability for TCT interfaces

TCT can send CLI and MCP tool invocations to Langfuse without decorating the
individual functions in `tools.py`. Instrumentation lives at the shared
interface invocation boundary:

```text
CLI ─┐
     ├─> invocation.invoke() ─> TCT tool
MCP ─┘           │
                 └─> optional Langfuse tool observation
```

Direct calls to the Python library do not cross this boundary and are not
observed. This keeps agent-facing observability separate from the core API
used by application and notebook developers.

## Default behavior

Langfuse is **disabled by default**. Installing the SDK or setting Langfuse
credentials does not enable it. TCT starts observations only when
`TCT_LANGFUSE_ENABLED` has an accepted true value.

| Variable | Required | Purpose |
| --- | --- | --- |
| `TCT_LANGFUSE_ENABLED` | Yes | Explicitly enables TCT instrumentation. Accepts `1`, `true`, `yes`, or `on`; matching false values disable it. |
| `LANGFUSE_PUBLIC_KEY` | Yes for normal SDK authentication | Langfuse project public key. |
| `LANGFUSE_SECRET_KEY` | Yes for normal SDK authentication | Langfuse project secret key. |
| `LANGFUSE_BASE_URL` | For self-hosted Langfuse | Langfuse API base URL; otherwise the SDK default applies. |
| `LANGFUSE_TRACING_ENVIRONMENT` | No | Labels traces by deployment environment. |

`LANGFUSE_TRACING_ENVIRONMENT` is separate from `TCT_ENVIRONMENT`.
`TCT_ENVIRONMENT` selects Translator service endpoints; it does not enable or
configure Langfuse.

## Install

Install only the capabilities required by the process:

```bash
# CLI observability
pip install 'TCT[langfuse]'

# MCP server and observability
pip install 'TCT[mcp,langfuse]'
```

From a source checkout with UV:

```bash
uv sync --extra langfuse
uv sync --extra mcp --extra langfuse
```

The Langfuse package is imported lazily. A normal TCT installation does not
need the SDK. If instrumentation is explicitly enabled without the optional
package, the CLI or MCP call reports that the `langfuse` extra must be
installed.

## Configure and run the CLI

Set credentials through the process environment and opt in explicitly:

```bash
export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export LANGFUSE_BASE_URL=https://cloud.langfuse.com
export LANGFUSE_TRACING_ENVIRONMENT=development
export TCT_LANGFUSE_ENABLED=true

uv run tct name-lookup --query aspirin
```

The CLI flushes pending Langfuse events before it exits. To disable tracing
while leaving credentials available:

```bash
TCT_LANGFUSE_ENABLED=false uv run tct name-lookup --query aspirin
```

## Configure and run the MCP server

The existing MCP entry point does not change:

```bash
export LANGFUSE_PUBLIC_KEY=your-public-key
export LANGFUSE_SECRET_KEY=your-secret-key
export TCT_LANGFUSE_ENABLED=true

uv run tct-server
```

An MCP client may pass the same variables to the server process. The exact
configuration shape depends on the client; a typical stdio configuration is:

```json
{
  "mcpServers": {
    "tct": {
      "command": "uv",
      "args": ["run", "tct-server"],
      "cwd": "/absolute/path/to/Translator_component_toolkit",
      "env": {
        "TCT_LANGFUSE_ENABLED": "true",
        "LANGFUSE_PUBLIC_KEY": "your-public-key",
        "LANGFUSE_SECRET_KEY": "your-secret-key"
      }
    }
  }
}
```

Do not commit real credentials in an MCP client configuration. Prefer the
client's secret storage or inherited process environment. The server batches
events while running and flushes them during normal shutdown.

## Observation contract

Each observed invocation uses the Langfuse observation type `tool` and the
name `tct.tool.<tool_name>`. For example, `name_lookup` appears as
`tct.tool.name_lookup`.

TCT attaches the following metadata:

| Metadata | Value |
| --- | --- |
| `tct.interface` | `cli` or `mcp` |
| `tct.module` | Python module containing the shared callable |
| `tct.tool` | Python callable name |
| `tct.input.bytes` | Canonical UTF-8 JSON size of all bound arguments |
| `tct.input.sha256` | Stable identity for detecting an exact repeated call |
| `tct.input.argument.<name>.bytes` | Canonical size of one argument |
| `tct.input.argument.<name>.sha256` | Stable identity of one repeated argument |
| `tct.output.bytes` | Canonical UTF-8 JSON size of the returned value |
| `tct.output.sha256` | Stable identity for detecting repeated results |

When applicable, observations also include `tct.provider.name`,
`tct.provider.count`, `tct.batch.item_count`, `tct.batch.argument`,
`tct.query.node_count`, `tct.query.identifier_count`, and
`tct.query.identifier_node_count`. These fields are derived from ordinary
arguments at the shared invocation boundary; individual tools do not require
observability decorators.

Inputs are bound against the Python signature, so the observation includes
applied default values as well as arguments supplied by the caller. Successful
outputs are converted to JSON-compatible values using the same normalization
conventions as CLI results. On failure, the original exception crosses the
Langfuse context before TCT converts it to its stable CLI or MCP error.

The hashes identify equal canonical payloads; they are not cache keys exposed
to callers and do not change invocation behavior. Input and output byte counts
measure TCT's normalized logical values, not model tokens or MCP wire framing.
An agent's Langfuse integration remains responsible for generation model,
token usage, and price. When agent and MCP observations share distributed
trace context, those generation costs and these tool metrics can be analyzed
within the same turn.

## Test the integration

Run the isolated tests, which use fakes and do not send data to Langfuse:

```bash
uv run pytest \
  tests/test_observability.py \
  tests/test_invocation.py \
  tests/test_cli.py \
  tests/test_server.py
```

Verify strict opt-in behavior directly:

```bash
LANGFUSE_PUBLIC_KEY=present \
LANGFUSE_SECRET_KEY=present \
uv run python -c \
  'from TCT.interfaces.observability import langfuse_enabled; assert not langfuse_enabled()'
```

For an end-to-end check, supply credentials, set
`TCT_LANGFUSE_ENABLED=true`, invoke a CLI command or an MCP tool, and look for
`tct.tool.<tool_name>` in the configured Langfuse project.

## Data handling

Observations may contain biomedical queries, identifiers, complete bound
arguments, and service responses. Enable this integration only when the
Langfuse deployment and project retention policy meet the data-handling
requirements of the environment.
