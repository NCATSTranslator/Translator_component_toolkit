# Langfuse per-turn payload baseline

The `langfuse-turns-v1` benchmark exercises the same metadata generation used
by TCT's Langfuse tool observations. It groups tool calls into representative
agent turns and compares one-call-per-identifier behavior with a batched call.

The fixture is deterministic, makes no network requests, and sends nothing to
Langfuse. Regenerate it with:

```bash
python -m benchmarks.langfuse_turns
```

| Metric | One by one | Batched | Duplicate batch |
| --- | ---: | ---: | ---: |
| Tool calls | 7 | 1 | 2 |
| Unique inputs | 7 | 1 | 1 |
| Repeated input calls | 0 | 0 | 1 |
| Input bytes | 10,269 | 1,563 | 3,126 |
| Output bytes | 679 | 457 | 914 |
| Total payload bytes | 10,948 | 2,020 | 4,040 |
| Repeated provider metadata bytes | 8,372 | 1,196 | 2,392 |

For seven identifiers, batching avoids six tool calls, 8,706 input bytes
(84.8%), and 8,928 total payload bytes (81.5%). It also avoids 7,176 bytes of
provider metadata that would otherwise be repeated within the turn.

These are tool-boundary payload measurements, not model token counts. Model
input/output tokens and price belong to the parent generation observation.
When the MCP client propagates the parent W3C trace context, Langfuse can join
those generation costs with TCT's tool-call counts, hashes, and payload sizes
for a complete per-turn view.

## Live acceptance: conversational turns returned by Langfuse

The offline benchmark is not proof that a Langfuse deployment accepted the
observations. The live acceptance probe creates two parent `agent`
observations, invokes the TCT fixture tools beneath them, flushes the SDK, and
then queries those trace IDs through the Langfuse observations API. Its JSON
output is computed only from observations returned by Langfuse.

Set `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`; set
`LANGFUSE_BASE_URL` as well for a self-hosted deployment. Then run:

```bash
uv run --extra langfuse python -m benchmarks.langfuse_conversation_acceptance
```

Exit status zero and `"acceptance": "passed"` mean that both conversational
turns and their TCT child observations were returned with metrics. Credentials
are required but are never included in the report or configuration errors.
The latest sanitized live result is checked in as
`langfuse_conversation_acceptance_result.json` so reviewers can inspect the
server-returned trace IDs and metrics directly in the pull request.
