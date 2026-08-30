#!/usr/bin/env bash
# Phase 5 demo -- interactive, open-ended driver. Handles all three possible
# outcomes for whatever question you type, uniformly:
#
#   - plain ALLOW (e.g. "Tell me about Akto Atlas") -> normal grounded
#     answer, no human involved at all
#   - deterministic APPROVAL_REQUIRED (e.g. asking it to submit feedback) ->
#     asks you, interactively, to approve/deny
#   - semantic HITL_REQUIRED (a DAST-related question) -> asks you,
#     interactively, to approve/deny/give an additional instruction
#
# You type the question; the Orchestrator's own deterministic keyword
# router decides which delegated agent handles it (API Security vs Agentic
# Security) -- nothing about the domain is hardcoded here, same as the real
# system. If a decision leads to a follow-up tool call that also needs a
# decision, this script loops and asks again (capped, see MAX_ROUNDS) --
# real agent behavior, not a bug (see scripts/test_hitl_flow.sh's header
# comment for the same note in more detail).
#
# scripts/test_approval_flow.sh and scripts/test_hitl_flow.sh are unchanged
# and still the right choice for the two fixed, scripted demo scenarios
# (sendFeedback approval, DAST HITL) with a non-interactive, canned human
# decision. This script is for ad hoc/open-ended demo questions instead.
#
# Requires: AWS CLI authenticated against this account. Uses python3's
# stdlib json module only -- no boto3, no jq.
#
# No account ID, runtime ID, or region is hardcoded here -- everything is
# resolved from `terraform output` in infra/environments/dev (or from your
# own environment variables, if you'd rather not depend on a local
# Terraform checkout -- see the RESOLVE block below for every variable
# name you can override).
#
# Usage:
#   scripts/demo_interactive.sh                   # prompts you for a question
#   scripts/demo_interactive.sh "your question"    # question given directly
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/dev"

# --- Resolve endpoints: environment variable override, else `terraform output` ---
tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

ORCHESTRATOR_ARN="${ORCHESTRATOR_ARN:-$(tf_output orchestrator_runtime_arn)}"
APPROVAL_AGENT_ARN="${APPROVAL_AGENT_ARN:-$(tf_output approval_agent_runtime_arn)}"
API_AGENT_ARN="${API_AGENT_ARN:-$(tf_output api_security_agent_runtime_arn)}"
AGENTIC_AGENT_ARN="${AGENTIC_AGENT_ARN:-$(tf_output agentic_security_agent_runtime_arn)}"
INTERCEPTOR_LOG_GROUP="${INTERCEPTOR_LOG_GROUP:-$(tf_output interceptor_log_group_name)}"

if [ -z "$ORCHESTRATOR_ARN" ] || [ -z "$APPROVAL_AGENT_ARN" ]; then
  echo "Could not resolve the Orchestrator/Approval Agent runtime ARNs." >&2
  echo "Either run this from a checkout with infra/environments/dev already" >&2
  echo "applied (so 'terraform output' succeeds), or export ORCHESTRATOR_ARN" >&2
  echo "and APPROVAL_AGENT_ARN yourself before running this script." >&2
  exit 1
fi

# Region is derived from the ARN itself (arn:aws:<service>:<region>:<account>:...)
# rather than assumed, so this works against any region without editing the script.
REGION="${REGION:-$(echo "$ORCHESTRATOR_ARN" | cut -d: -f4)}"
REGION="${REGION:-us-east-1}"

runtime_id_from_arn() { echo "${1##*/}"; }
ORCHESTRATOR_LOG_GROUP="/aws/bedrock-agentcore/runtimes/$(runtime_id_from_arn "$ORCHESTRATOR_ARN")-DEFAULT"

MAX_ROUNDS=6
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
step() { echo; bold "=== $1 ==="; }
json_string() { python3 -c 'import json, sys; print(json.dumps(sys.argv[1]))' "$1"; }
json_get() {
  python3 - "$1" "$2" <<'PYEOF'
import json, sys
data = json.load(open(sys.argv[1]))
for key in sys.argv[2].split("."):
    data = data.get(key) if isinstance(data, dict) else None
    if data is None:
        break
print(data if data is not None else "")
PYEOF
}
# CloudWatch Logs access is a nice-to-have for this script (the delegation
# trace / evidence steps), not required for the actual approve/deny/resume
# flow -- so a permissions failure here (e.g. a narrowly-scoped credential
# shared with someone who only has invoke, not logs, access) prints a note
# and continues instead of aborting the whole demo via `set -e`.
try_logs() {
  if ! aws logs filter-log-events "$@" --query "events[].message" --output text 2>"$WORKDIR/logs_err"; then
    echo "(couldn't read this log group -- likely missing logs:FilterLogEvents; skipping)" >&2
    head -1 "$WORKDIR/logs_err" >&2 || true
  fi
}

delegate_log_group() {
  case "$1" in
    api_security)
      [ -n "$API_AGENT_ARN" ] && echo "/aws/bedrock-agentcore/runtimes/$(runtime_id_from_arn "$API_AGENT_ARN")-DEFAULT"
      ;;
    agentic_security)
      [ -n "$AGENTIC_AGENT_ARN" ] && echo "/aws/bedrock-agentcore/runtimes/$(runtime_id_from_arn "$AGENTIC_AGENT_ARN")-DEFAULT"
      ;;
    *) echo "" ;;
  esac
}

PROMPT="${1:-}"
if [ -z "$PROMPT" ]; then
  echo "Enter your question for the Agent Security Lab -- try a normal"
  echo "documentation question, ask it to submit feedback, or ask about DAST:"
  read -r -p "> " PROMPT
fi

step "Sending your question to the Orchestrator"
echo "Prompt: $PROMPT"
TRIGGER_START_MS=$(( $(date +%s) * 1000 ))
printf '{"prompt": %s}' "$(json_string "$PROMPT")" > "$WORKDIR/request.json"
aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "$ORCHESTRATOR_ARN" \
  --payload "fileb://$WORKDIR/request.json" --region "$REGION" \
  "$WORKDIR/response.json" >/dev/null
python3 -m json.tool < "$WORKDIR/response.json"

DOMAIN=$(json_get "$WORKDIR/response.json" domain)
DELEGATE_LOG_GROUP="$(delegate_log_group "$DOMAIN")"
if [ -n "$DELEGATE_LOG_GROUP" ]; then
  step "Delegation trace: Orchestrator -> A2A -> $DOMAIN agent"
  echo "(waiting 8s for CloudWatch Logs to ingest...)"
  sleep 8
  echo "--- Orchestrator's own log ---"
  try_logs --region "$REGION" --log-group-name "$ORCHESTRATOR_LOG_GROUP" \
    --start-time "$TRIGGER_START_MS" --filter-pattern "Delegating to"
  echo
  echo "--- Delegated agent's own log (health-check noise filtered out) ---"
  try_logs --region "$REGION" --log-group-name "$DELEGATE_LOG_GROUP" \
    --start-time "$TRIGGER_START_MS" --filter-pattern '-"GET /ping"'
fi

ROUND=0
while true; do
  STATUS=$(json_get "$WORKDIR/response.json" status)

  case "$STATUS" in
    success)
      step "Result: ALLOWED / completed, no human needed (or already resolved)"
      json_get "$WORKDIR/response.json" response
      break
      ;;
    clarification_needed)
      step "Result: ambiguous question"
      json_get "$WORKDIR/response.json" response
      break
      ;;
    error)
      step "Result: error"
      json_get "$WORKDIR/response.json" response
      break
      ;;
    approval_required|hitl_required)
      ROUND=$((ROUND + 1))
      if [ "$ROUND" -gt "$MAX_ROUNDS" ]; then
        bold "Stopping after $MAX_ROUNDS rounds of human decisions to avoid an unbounded loop."
        break
      fi

      KIND_LABEL="deterministic approval"
      [ "$STATUS" = "hitl_required" ] && KIND_LABEL="human-in-the-loop (semantic)"
      REFERENCE_ID=$(json_get "$WORKDIR/response.json" resume_token.reference_id)

      step "Human decision required -- $KIND_LABEL (round $ROUND)"
      echo "Reference: $REFERENCE_ID"
      echo "Question for you, the reviewer:"
      echo "  $(json_get "$WORKDIR/response.json" response)"
      echo
      if [ "$STATUS" = "hitl_required" ]; then
        read -r -p "Decision? [approve/deny/instruct]: " DECISION
      else
        read -r -p "Decision? [approve/deny]: " DECISION
      fi

      case "$DECISION" in
        approve|deny)
          printf '{"action": "decide", "reference_id": "%s", "decision": "%s", "approver": "interactive-demo"}' \
            "$REFERENCE_ID" "$DECISION" > "$WORKDIR/decide.json"
          ;;
        instruct)
          if [ "$STATUS" != "hitl_required" ]; then
            echo "Additional instructions only apply to HITL requests, not deterministic approvals -- treating as deny." >&2
            printf '{"action": "decide", "reference_id": "%s", "decision": "deny", "approver": "interactive-demo"}' \
              "$REFERENCE_ID" > "$WORKDIR/decide.json"
          else
            read -r -p "Instruction text: " INSTRUCTION_TEXT
            python3 -c "
import json
payload = {'action': 'decide', 'reference_id': '$REFERENCE_ID', 'decision': 'instruction',
           'instruction_text': $(json_string "$INSTRUCTION_TEXT"), 'approver': 'interactive-demo'}
json.dump(payload, open('$WORKDIR/decide.json', 'w'))
"
          fi
          ;;
        *)
          echo "Unrecognized input '$DECISION' -- treating as deny." >&2
          printf '{"action": "decide", "reference_id": "%s", "decision": "deny", "approver": "interactive-demo"}' \
            "$REFERENCE_ID" > "$WORKDIR/decide.json"
          ;;
      esac

      aws bedrock-agentcore invoke-agent-runtime \
        --agent-runtime-arn "$APPROVAL_AGENT_ARN" \
        --payload "fileb://$WORKDIR/decide.json" --region "$REGION" \
        "$WORKDIR/decide_response.json" >/dev/null
      python3 -m json.tool < "$WORKDIR/decide_response.json"

      GRANT=$(json_get "$WORKDIR/decide_response.json" grant)
      if [ -n "$GRANT" ]; then
        echo "-> Signed grant issued (AWS KMS, short-lived, single-use)."
      else
        echo "-> No grant issued."
      fi

      step "Resuming the paused workflow"
      python3 -c "
import json
d = json.load(open('$WORKDIR/response.json'))
json.dump({'resume_token': d['resume_token']}, open('$WORKDIR/resume.json', 'w'))
"
      aws bedrock-agentcore invoke-agent-runtime \
        --agent-runtime-arn "$ORCHESTRATOR_ARN" \
        --payload "fileb://$WORKDIR/resume.json" --region "$REGION" \
        "$WORKDIR/response.json" >/dev/null
      python3 -m json.tool < "$WORKDIR/response.json"
      ;;
    *)
      echo "Unexpected status: $STATUS" >&2
      break
      ;;
  esac
done

if [ -n "$INTERCEPTOR_LOG_GROUP" ]; then
  step "Evidence: interceptor's last few decisions"
  echo "(waiting 10s for CloudWatch Logs to ingest...)"
  sleep 10
  START_MS=$(( ($(date +%s) - 90) * 1000 ))
  try_logs --region "$REGION" --log-group-name "$INTERCEPTOR_LOG_GROUP" \
    --start-time "$START_MS"
fi

echo
bold "Demo complete."
