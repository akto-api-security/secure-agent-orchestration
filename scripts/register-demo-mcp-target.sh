#!/usr/bin/env bash
# Register the demo guardrails MCP server on the existing AgentCore MCP Gateway.
#
# Reads the endpoint from examples/demo-guardrails-mcp/.endpoint (written by
# deploy-demo-mcp-server.sh) or DEMO_GUARDRAILS_MCP_ENDPOINT.
#
# Usage: scripts/register-demo-mcp-target.sh [mcp-endpoint-url]
# Set AUTO_APPROVE=1 to skip prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/akto-demo"
ENDPOINT_FILE="$ROOT_DIR/examples/demo-guardrails-mcp/.endpoint"

REGION="${AWS_REGION:-us-east-1}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  [ -n "${AUTO_APPROVE:-}" ] && return 0
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

APPROVE_FLAG=()
[ -n "${AUTO_APPROVE:-}" ] && APPROVE_FLAG=(-auto-approve)

ENDPOINT="${1:-${DEMO_GUARDRAILS_MCP_ENDPOINT:-}}"
if [ -z "$ENDPOINT" ] && [ -f "$ENDPOINT_FILE" ]; then
  ENDPOINT="$(tr -d '[:space:]' < "$ENDPOINT_FILE")"
fi

if [ -z "$ENDPOINT" ]; then
  echo "Pass the MCP endpoint URL or run scripts/deploy-demo-mcp-server.sh first." >&2
  exit 1
fi

if ! confirm "Add demo-guardrails-mcp target (${ENDPOINT}) to MCP Gateway?"; then
  echo "Aborted."
  exit 0
fi

if [[ "$ENDPOINT" != https://* ]]; then
  ENDPOINT="https://${ENDPOINT#https://}"
  ENDPOINT="https://${ENDPOINT#http://}"
fi

GATEWAY_ID="${MCP_GATEWAY_ID:-}"
if [ -z "$GATEWAY_ID" ] && [ -f "$TF_DIR/backend.hcl" ]; then
  GATEWAY_ID="$(terraform -chdir="$TF_DIR" output -raw mcp_gateway_id 2>/dev/null || true)"
fi
GATEWAY_ID="${GATEWAY_ID:-asl-gateway-demo-9lzr1onrx9}"

bold "=== create gateway target demo-guardrails-mcp (CLI) ==="
EXISTING="$(aws bedrock-agentcore-control list-gateway-targets \
  --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
  --query "items[?name=='demo-guardrails-mcp'].targetId | [0]" --output text 2>/dev/null || true)"
if [ -n "$EXISTING" ] && [ "$EXISTING" != "None" ]; then
  aws bedrock-agentcore-control delete-gateway-target \
    --gateway-identifier "$GATEWAY_ID" --target-id "$EXISTING" --region "$REGION" >/dev/null || true
  echo "Removed previous target ${EXISTING}"
  sleep 5
fi

CREATE_OUT="$(aws bedrock-agentcore-control create-gateway-target \
  --gateway-identifier "$GATEWAY_ID" \
  --region "$REGION" \
  --name demo-guardrails-mcp \
  --description "Akto guardrails demo MCP tools (email, webhook, refund, SQL, scrape)" \
  --target-configuration "{\"mcp\":{\"mcpServer\":{\"endpoint\":\"${ENDPOINT}\"}}}")"
TARGET_ID="$(printf '%s' "$CREATE_OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["targetId"])')"
echo "Created target ${TARGET_ID}"

bold "=== wait for READY ==="
for _ in $(seq 1 30); do
  STATUS="$(aws bedrock-agentcore-control get-gateway-target \
    --gateway-identifier "$GATEWAY_ID" --target-id "$TARGET_ID" --region "$REGION" \
    --query status --output text 2>/dev/null || echo UNKNOWN)"
  REASON="$(aws bedrock-agentcore-control get-gateway-target \
    --gateway-identifier "$GATEWAY_ID" --target-id "$TARGET_ID" --region "$REGION" \
    --query 'statusReasons[0]' --output text 2>/dev/null || true)"
  echo "  status: ${STATUS}${REASON:+ ($REASON)}"
  if [ "$STATUS" = "READY" ]; then
    break
  fi
  if [ "$STATUS" = "FAILED" ]; then
    echo "Gateway target failed." >&2
    exit 1
  fi
  sleep 5
done

MCP_GATEWAY_URL="$(aws bedrock-agentcore-control get-gateway \
  --gateway-identifier "$GATEWAY_ID" --region "$REGION" \
  --query 'gatewayUrl' --output text 2>/dev/null || true)"
MCP_GATEWAY_URL="${MCP_GATEWAY_URL:-https://${GATEWAY_ID}.gateway.bedrock-agentcore.${REGION}.amazonaws.com/mcp}"
[[ "$MCP_GATEWAY_URL" != */mcp ]] && MCP_GATEWAY_URL="${MCP_GATEWAY_URL%/}/mcp"

bold "=== done ==="
echo "MCP Gateway: ${MCP_GATEWAY_URL}"
echo "Target prefix: demo-guardrails-mcp"
echo
echo "Test:"
echo "  export MCP_GATEWAY_URL=\"\$(terraform -chdir=${TF_DIR} output -raw mcp_gateway_url)\""
echo "  export MCP_TARGET_PREFIX=demo-guardrails-mcp"
echo "  scripts/mcp-call.py list"
echo "  scripts/mcp-call.py call drop_table_mysql '{\"table_name\":\"users\"}'"
