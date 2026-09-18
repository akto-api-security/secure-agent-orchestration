#!/usr/bin/env bash
# Prove the Rovo demo path reaches its Runtime and demo-guardrails-mcp tools.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESPONSE="$("$SCRIPT_DIR/invoke-rovo-demo.sh" \
  "Search Jira for open security tickets and summarize the top priorities.")"

printf '%s\n' "$RESPONSE"

STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", ""))' <<<"$RESPONSE")"
if [ "$STATUS" != "success" ]; then
  echo "Rovo smoke test failed: expected status=success, got ${STATUS:-<missing>}." >&2
  exit 1
fi

echo "Rovo smoke test passed: rovo HTTP Gateway -> Runtime -> MCP Gateway -> demo-guardrails-mcp."
