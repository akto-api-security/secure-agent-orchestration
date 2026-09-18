#!/usr/bin/env bash
# Deploy Client -> HTTP Gateway -> Runtime -> MCP Gateway -> tools (ECR image).
# For the prebuilt zip (no Docker), use scripts/deploy-zip.sh instead.
# Usage: scripts/deploy.sh [image-tag]
# Set AUTO_APPROVE=1 to skip the prompts and Terraform approvals.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/akto-demo"
BOOTSTRAP_DIR="$ROOT_DIR/infra/bootstrap"
DOCS_AGENT_DIR="$ROOT_DIR/agents/akto-demo-agent"
ROVO_AGENT_DIR="$ROOT_DIR/agents/rovo-demo-agent"

VERSION="${1:-build-$(date -u +%Y%m%d%H%M%S)}"
REGION="${AWS_REGION:-us-east-1}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  [ -n "${AUTO_APPROVE:-}" ] && return 0
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

APPROVE_FLAG=()
[ -n "${AUTO_APPROVE:-}" ] && APPROVE_FLAG=(-auto-approve)

if [ ! -f "$TF_DIR/backend.hcl" ]; then
  BUCKET="$(terraform -chdir="$BOOTSTRAP_DIR" output -raw state_bucket_name 2>/dev/null || true)"
  if [ -z "$BUCKET" ]; then
    echo "No Terraform state backend found. Run scripts/bootstrap.sh first." >&2
    exit 1
  fi
  cat > "$TF_DIR/backend.hcl" <<EOF
bucket = "$BUCKET"
region = "$REGION"
EOF
  echo "Wrote $TF_DIR/backend.hcl."
fi

TF_VARS=(
  -var="image_tag=${VERSION}"
  -var="aws_region=${REGION}"
)

bold "=== AgentCore topology deploy, image=$VERSION ==="
echo "Creates two HTTP Gateways, two Runtimes, one shared MCP Gateway,"
echo "MCP targets (docs + demo-guardrails), ECR repos, and least-privilege IAM."
echo

if ! confirm "Continue?"; then
  echo "Aborted."
  exit 0
fi

bold "=== terraform init ==="
terraform -chdir="$TF_DIR" init -backend-config=backend.hcl

bold "=== create ECR repositories ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_VARS[@]}" \
  "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}" \
  -target=module.demo_agent.aws_ecr_repository.this \
  -target=module.rovo_demo_agent.aws_ecr_repository.this

DOCS_REPO_URL="$(terraform -chdir="$TF_DIR" output -raw demo_agent_ecr_repository_url)"
ROVO_REPO_URL="$(terraform -chdir="$TF_DIR" output -raw rovo_demo_agent_ecr_repository_url)"
if [ -z "$DOCS_REPO_URL" ] || [ -z "$ROVO_REPO_URL" ]; then
  echo "Could not read ECR repository URLs." >&2
  exit 1
fi

REGISTRY="${DOCS_REPO_URL%%/*}"
bold "=== build and push agent images ($VERSION) ==="
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 -t "${DOCS_REPO_URL}:${VERSION}" --push "$DOCS_AGENT_DIR"
docker buildx build --platform linux/arm64 -t "${ROVO_REPO_URL}:${VERSION}" --push "$ROVO_AGENT_DIR"

bold "=== deploy complete topology ==="
terraform -chdir="$TF_DIR" apply "${TF_VARS[@]}" "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}"

bold "=== done ==="
echo "Docs HTTP Gateway:  $(terraform -chdir="$TF_DIR" output -raw http_gateway_url)"
echo "Docs HTTP target:   $(terraform -chdir="$TF_DIR" output -raw http_gateway_target_name)"
echo "Docs Runtime:       $(terraform -chdir="$TF_DIR" output -raw demo_agent_runtime_arn)"
echo "Rovo HTTP Gateway:  $(terraform -chdir="$TF_DIR" output -raw rovo_http_gateway_url)"
echo "Rovo HTTP target:   $(terraform -chdir="$TF_DIR" output -raw rovo_http_gateway_target_name)"
echo "Rovo Runtime:       $(terraform -chdir="$TF_DIR" output -raw rovo_demo_agent_runtime_arn)"
echo "MCP Gateway:        $(terraform -chdir="$TF_DIR" output -raw mcp_gateway_url)"
echo
echo "Docs agent:"
echo "  scripts/invoke.sh \"What does API security testing cover?\""
echo "  scripts/smoke-test.sh"
echo "Rovo demo agent:"
echo "  scripts/invoke-rovo-demo.sh \"I uploaded a Backlog Guide. Organize my Jira backlog.\""
echo "  scripts/smoke-test-rovo-demo.sh"
