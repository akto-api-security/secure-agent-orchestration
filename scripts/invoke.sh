#!/usr/bin/env bash
# Invoke the agent through the outer HTTP Gateway.
# Usage: scripts/invoke.sh "What does API security testing cover?"
#
# Override stale Terraform outputs when the live stack was created in the
# console (set all three before calling):
#   export HTTP_GATEWAY_URL=...
#   export HTTP_GATEWAY_TARGET=demo-agent
#   export AGENT_RUNTIME_ARN=...
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/akto-demo"
PROMPT="${1:-What does API security testing cover in Akto?}"
REGION="${AWS_REGION:-us-east-1}"
READ_TIMEOUT="${INVOKE_READ_TIMEOUT:-900}"

if [ -n "${AWS_PROFILE:-}" ]; then
  export AWS_SDK_LOAD_CONFIG=1
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
fi

if [ -n "${HTTP_GATEWAY_URL:-}" ]; then
  GATEWAY_URL="$HTTP_GATEWAY_URL"
else
  GATEWAY_URL="$(terraform -chdir="$TF_DIR" output -raw http_gateway_url)"
fi

if [ -n "${HTTP_GATEWAY_TARGET:-}" ]; then
  TARGET_NAME="$HTTP_GATEWAY_TARGET"
else
  TARGET_NAME="$(terraform -chdir="$TF_DIR" output -raw http_gateway_target_name)"
fi

if [ -n "${AGENT_RUNTIME_ARN:-}" ]; then
  RUNTIME_ARN="$AGENT_RUNTIME_ARN"
else
  RUNTIME_ARN="$(terraform -chdir="$TF_DIR" output -raw demo_agent_runtime_arn)"
fi

ENDPOINT_URL="${GATEWAY_URL%/}/${TARGET_NAME}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

python3 -c 'import json,sys; json.dump({"prompt": sys.argv[1]}, sys.stdout)' "$PROMPT" > "$WORKDIR/payload.json"

echo "endpoint:  ${ENDPOINT_URL}" >&2
echo "runtime:   ${RUNTIME_ARN}" >&2
echo "region:    ${REGION}" >&2

AWS_ARGS=()
[ -n "${AWS_PROFILE:-}" ] && AWS_ARGS=(--profile "$AWS_PROFILE")

if ! aws "${AWS_ARGS[@]}" bedrock-agentcore invoke-agent-runtime \
  --endpoint-url "$ENDPOINT_URL" \
  --agent-runtime-arn "$RUNTIME_ARN" \
  --qualifier DEFAULT \
  --payload "fileb://$WORKDIR/payload.json" \
  --region "$REGION" \
  --cli-read-timeout "$READ_TIMEOUT" \
  "$WORKDIR/response.json"; then
  if [ -s "$WORKDIR/response.json" ]; then
    echo "response body:" >&2
    python3 -m json.tool "$WORKDIR/response.json" >&2 || cat "$WORKDIR/response.json" >&2
  fi
  echo "If the error is ExpiredTokenException, refresh AWS credentials." >&2
  echo "If 403, Akto guardrails likely blocked the request (expected for blocked prompts)." >&2
  echo "If InternalFailure, check Runtime and interceptor CloudWatch logs." >&2
  exit 1
fi

python3 -m json.tool "$WORKDIR/response.json"
