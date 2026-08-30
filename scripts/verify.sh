#!/usr/bin/env bash
# Phase 6 -- post-deploy smoke test. Read-only against every resource
# except one benign Orchestrator invoke (a plain API Security question,
# same class of request Phase 3 already used for its own live tests) --
# nothing here approves/denies/mutates any approval or infrastructure
# state.
#
# Exit code 0 = every check passed, 1 = at least one failed.
#
# Usage: scripts/verify.sh
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/dev"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

ORCHESTRATOR_ARN="${ORCHESTRATOR_ARN:-$(tf_output orchestrator_runtime_arn)}"
API_AGENT_ARN="${API_AGENT_ARN:-$(tf_output api_security_agent_runtime_arn)}"
AGENTIC_AGENT_ARN="${AGENTIC_AGENT_ARN:-$(tf_output agentic_security_agent_runtime_arn)}"
APPROVAL_AGENT_ARN="${APPROVAL_AGENT_ARN:-$(tf_output approval_agent_runtime_arn)}"
GATEWAY_ID="${GATEWAY_ID:-$(tf_output gateway_id)}"
REGION="${REGION:-$(echo "$ORCHESTRATOR_ARN" | cut -d: -f4)}"
REGION="${REGION:-us-east-1}"

runtime_id_from_arn() { echo "${1##*/}"; }

PASS=0
FAIL=0
check() {
  local label="$1" result="$2"
  if [ "$result" = "ok" ]; then
    printf '  [PASS] %s\n' "$label"
    PASS=$((PASS + 1))
  else
    printf '  [FAIL] %s -- %s\n' "$label" "$result"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== Runtime status ==="
for pair in "Orchestrator:$ORCHESTRATOR_ARN" "API Security Agent:$API_AGENT_ARN" \
            "Agentic Security Agent:$AGENTIC_AGENT_ARN" "Approval Agent:$APPROVAL_AGENT_ARN"; do
  name="${pair%%:*}"
  arn="${pair#*:}"
  if [ -z "$arn" ]; then
    check "$name runtime status" "ARN not resolved (terraform output empty and no override env var set)"
    continue
  fi
  status=$(aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$(runtime_id_from_arn "$arn")" \
    --region "$REGION" --query "status" --output text 2>&1)
  if [ "$status" = "READY" ]; then
    check "$name runtime status" "ok"
  else
    check "$name runtime status" "expected READY, got: $status"
  fi
done

echo
echo "=== Gateway target sync ==="
if [ -n "$GATEWAY_ID" ]; then
  targets=$(aws bedrock-agentcore-control list-gateway-targets --gateway-identifier "$GATEWAY_ID" \
    --region "$REGION" --query "items[].status" --output text 2>&1)
  if [ -n "$targets" ] && ! echo "$targets" | grep -qv "READY\|SUCCESS"; then
    check "Gateway targets synced" "ok"
  else
    check "Gateway targets synced" "not all READY/SUCCESS: $targets"
  fi
else
  check "Gateway targets synced" "gateway_id not resolved"
fi

echo
echo "=== Live end-to-end invoke (a real question, routed through the full chain) ==="
if [ -n "$ORCHESTRATOR_ARN" ]; then
  printf '{"prompt": "What is prompt injection and how does Akto test for it?"}' > "$WORKDIR/payload.json"
  if aws bedrock-agentcore invoke-agent-runtime --agent-runtime-arn "$ORCHESTRATOR_ARN" \
      --payload "fileb://$WORKDIR/payload.json" --region "$REGION" "$WORKDIR/response.json" >/dev/null 2>"$WORKDIR/err"; then
    resp_status=$(python3 -c "import json; print(json.load(open('$WORKDIR/response.json')).get('status',''))" 2>/dev/null || echo "")
    # success / approval_required / hitl_required are all valid proof the
    # full chain (Orchestrator -> A2A -> Gateway -> Interceptor -> Approval
    # Agent) actually ran -- the Approval Agent's semantic rule is a real
    # LLM call and can legitimately request HITL for a given question, so
    # this isn't treated as a failure the way a plain "error" status is.
    case "$resp_status" in
      success|approval_required|hitl_required)
        check "Orchestrator end-to-end invoke" "ok"
        ;;
      *)
        check "Orchestrator end-to-end invoke" "unexpected status in response: $resp_status"
        ;;
    esac
  else
    check "Orchestrator end-to-end invoke" "invoke-agent-runtime failed: $(cat "$WORKDIR/err")"
  fi
else
  check "Orchestrator end-to-end invoke" "orchestrator ARN not resolved"
fi

echo
echo "=== Summary: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]
