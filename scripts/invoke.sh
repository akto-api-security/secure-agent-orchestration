#!/usr/bin/env bash
# Invoke the agent through the outer HTTP Gateway.
# Usage: scripts/invoke.sh "What does API security testing cover?"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/akto-demo"
PROMPT="${1:-What does API security testing cover in Akto?}"
REGION="${AWS_REGION:-us-east-1}"
GATEWAY_URL="${HTTP_GATEWAY_URL:-$(terraform -chdir="$TF_DIR" output -raw http_gateway_url)}"
TARGET_NAME="${HTTP_GATEWAY_TARGET:-$(terraform -chdir="$TF_DIR" output -raw http_gateway_target_name)}"
RUNTIME_ARN="${AGENT_RUNTIME_ARN:-$(terraform -chdir="$TF_DIR" output -raw demo_agent_runtime_arn)}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

python3 -c 'import json,sys; json.dump({"prompt": sys.argv[1]}, sys.stdout)' "$PROMPT" > "$WORKDIR/payload.json"

aws bedrock-agentcore invoke-agent-runtime \
  --endpoint-url "${GATEWAY_URL%/}/${TARGET_NAME}" \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --qualifier DEFAULT \
  --payload "fileb://$WORKDIR/payload.json" \
  --region "$REGION" \
  "$WORKDIR/response.json" >/dev/null

python3 -m json.tool "$WORKDIR/response.json"
