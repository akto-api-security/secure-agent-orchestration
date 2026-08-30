#!/usr/bin/env bash
# Phase 6 -- resolves the same runtime ARNs/log groups
# scripts/demo_interactive.sh already resolves (env var override, else
# `terraform output`), exports them, and launches the lightweight demo UI
# (ui/) against the already-deployed backend. The UI never talks to the
# Gateway or MCP directly -- only the Orchestrator and Approval Agent
# runtimes, same as every other demo script in this repo.
#
# Usage: scripts/start-demo.sh [port]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/dev"
UI_DIR="$ROOT_DIR/ui"
PORT="${1:-8000}"

tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

export ORCHESTRATOR_ARN="${ORCHESTRATOR_ARN:-$(tf_output orchestrator_runtime_arn)}"
export APPROVAL_AGENT_ARN="${APPROVAL_AGENT_ARN:-$(tf_output approval_agent_runtime_arn)}"
export API_AGENT_ARN="${API_AGENT_ARN:-$(tf_output api_security_agent_runtime_arn)}"
export AGENTIC_AGENT_ARN="${AGENTIC_AGENT_ARN:-$(tf_output agentic_security_agent_runtime_arn)}"
export INTERCEPTOR_LOG_GROUP="${INTERCEPTOR_LOG_GROUP:-$(tf_output interceptor_log_group_name)}"
export REGION="${REGION:-$(echo "$ORCHESTRATOR_ARN" | cut -d: -f4)}"
export REGION="${REGION:-us-east-1}"

if [ -z "$ORCHESTRATOR_ARN" ] || [ -z "$APPROVAL_AGENT_ARN" ]; then
  echo "Could not resolve the Orchestrator/Approval Agent runtime ARNs." >&2
  echo "Either run this from a checkout with infra/environments/dev already" >&2
  echo "applied (so 'terraform output' succeeds), or export ORCHESTRATOR_ARN" >&2
  echo "and APPROVAL_AGENT_ARN yourself before running this script." >&2
  exit 1
fi

VENV_DIR="$UI_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --quiet -r "$UI_DIR/backend/requirements.txt"

echo
echo "Starting demo UI on http://localhost:$PORT -- Ctrl+C to stop."
cd "$UI_DIR" && exec python3 -m uvicorn backend.app:app --host 0.0.0.0 --port "$PORT"
