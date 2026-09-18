#!/usr/bin/env bash
# Invoke the Rovo-style demo agent through its dedicated HTTP Gateway.
# Usage: scripts/invoke-rovo-demo.sh "I uploaded a Backlog Guide. Organize my Jira backlog."
#
# Override stale Terraform outputs when needed:
#   export ROVO_HTTP_GATEWAY_URL=...
#   export ROVO_HTTP_GATEWAY_TARGET=rovo-demo-agent
#   export ROVO_AGENT_RUNTIME_ARN=...
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/akto-demo"
PROMPT="${1:-I uploaded a Backlog Guide. Please read it and organize my Jira backlog for this sprint.}"
REGION="${AWS_REGION:-us-east-1}"
READ_TIMEOUT="${INVOKE_READ_TIMEOUT:-900}"

# Stale AWS_ACCESS_KEY_ID env vars override a fresh profile/SSO login and break
# terraform output (S3 backend). Prefer the profile when set.
if [ -n "${AWS_PROFILE:-}" ]; then
  export AWS_SDK_LOAD_CONFIG=1
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
fi

if [ -n "${ROVO_HTTP_GATEWAY_URL:-}" ]; then
  GATEWAY_URL="$ROVO_HTTP_GATEWAY_URL"
else
  GATEWAY_URL="$(terraform -chdir="$TF_DIR" output -raw rovo_http_gateway_url)"
fi

if [ -n "${ROVO_HTTP_GATEWAY_TARGET:-}" ]; then
  TARGET_NAME="$ROVO_HTTP_GATEWAY_TARGET"
else
  TARGET_NAME="$(terraform -chdir="$TF_DIR" output -raw rovo_http_gateway_target_name)"
fi

if [ -n "${ROVO_AGENT_RUNTIME_ARN:-}" ]; then
  RUNTIME_ARN="$ROVO_AGENT_RUNTIME_ARN"
else
  RUNTIME_ARN="$(terraform -chdir="$TF_DIR" output -raw rovo_demo_agent_runtime_arn)"
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
