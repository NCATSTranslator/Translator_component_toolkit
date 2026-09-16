#!/bin/sh
set -eu

env_file=${1:-./.env}
case "$env_file" in
    */*) ;;
    *) env_file="./$env_file" ;;
esac

if [ ! -f "$env_file" ]; then
    echo "Langfuse environment file not found: $env_file" >&2
    exit 2
fi

set -a
. "$env_file"
set +a

: "${LANGFUSE_PUBLIC_KEY:?LANGFUSE_PUBLIC_KEY is required}"
: "${LANGFUSE_SECRET_KEY:?LANGFUSE_SECRET_KEY is required}"
: "${LANGFUSE_BASE_URL:?LANGFUSE_BASE_URL is required}"

mkdir -p .codex
umask 077
temporary_file=$(mktemp .codex/langfuse.json.XXXXXX)
trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

jq -n \
    --arg public_key "$LANGFUSE_PUBLIC_KEY" \
    --arg secret_key "$LANGFUSE_SECRET_KEY" \
    --arg base_url "$LANGFUSE_BASE_URL" \
    '{
        enabled: true,
        public_key: $public_key,
        secret_key: $secret_key,
        base_url: $base_url,
        environment: "development",
        tags: ["tct", "codex"]
    }' > "$temporary_file"

mv "$temporary_file" .codex/langfuse.json
chmod 600 .codex/langfuse.json
trap - EXIT HUP INT TERM

echo "Configured Codex Langfuse tracing in .codex/langfuse.json (mode 600)."
echo "The file is ignored by git; credential values were not printed."
