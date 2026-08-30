#!/usr/bin/env bash
# Consolidated deploy -- runs README.md's Steps 6-10 in one go: terraform
# init, create the 4 ECR repos, build+push all 4 images, deploy everything
# else, then verify.
#
# Assumes infra/bootstrap has already been run (scripts/bootstrap.sh) and
# infra/environments/dev/backend.hcl exists -- this script does NOT create
# the state backend itself. That's a rarer, one-time, separate step (same
# reasoning as scripts/destroy.sh keeping backend removal separate).
#
# Every terraform apply below still runs interactively (no -auto-approve),
# so you see and approve each real plan yourself -- this script only
# chains the commands, it doesn't remove your review of what changes.
#
# Usage: scripts/deploy.sh [version]
#   version defaults to the current git short SHA (same default
#   scripts/build-and-push.sh uses).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/dev"

VERSION="${1:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "manual-$(date +%Y%m%d%H%M%S)")}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

if [ ! -f "$TF_DIR/backend.hcl" ]; then
  echo "No $TF_DIR/backend.hcl found -- run scripts/bootstrap.sh first (creates the Terraform state backend)." >&2
  exit 1
fi

bold "=== This will deploy the full stack into infra/environments/dev, version=$VERSION ==="
echo "That's: 4 ECR repos, 4 AgentCore Runtimes (Orchestrator, API/Agentic"
echo "Security Agents, Approval Agent), the Gateway, the interceptor Lambda,"
echo "a DynamoDB table, a KMS key, and all IAM roles/policies. Each"
echo "terraform apply below shows its own plan and asks for its own"
echo "confirmation too."
echo

if ! confirm "Continue?"; then
  echo "Aborted."
  exit 0
fi

bold "=== Step 1/4: terraform init ==="
(cd "$TF_DIR" && terraform init -backend-config=backend.hcl)

bold "=== Step 2/4: create the 4 ECR repositories ==="
(cd "$TF_DIR" && terraform apply \
  -target=module.orchestrator.aws_ecr_repository.this \
  -target=module.api_security_agent.aws_ecr_repository.this \
  -target=module.agentic_security_agent.aws_ecr_repository.this \
  -target=module.approval_agent.aws_ecr_repository.this)

bold "=== Step 3/4: build and push all 4 images (version=$VERSION) ==="
"$SCRIPT_DIR/build-and-push.sh" "$VERSION"

bold "=== Step 4/4: deploy everything else ==="
(cd "$TF_DIR" && terraform apply -var="image_tag=$VERSION")

bold "=== Verifying ==="
"$SCRIPT_DIR/verify.sh"

bold "=== Done ==="
echo "Run scripts/start-demo.sh whenever you're ready to try the UI."
