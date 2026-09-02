#!/usr/bin/env bash
# Prove the public path reaches the Runtime and its MCP tools.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESPONSE="$("$SCRIPT_DIR/invoke.sh" \
  "Use the Akto documentation tools to explain what API security testing covers.")"

printf '%s\n' "$RESPONSE"

STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))' <<<"$RESPONSE")"
if [ "$STATUS" != "success" ]; then
  echo "Smoke test failed: expected status=success, got ${STATUS:-<missing>}." >&2
  exit 1
fi

echo "Smoke test passed: HTTP Gateway -> Runtime -> MCP Gateway -> tool."
