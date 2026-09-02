#!/usr/bin/env bash
# Deploy Client -> HTTP Gateway -> Runtime -> MCP Gateway -> tools.
# Usage: scripts/deploy.sh [image-tag]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/akto-demo"
BOOTSTRAP_DIR="$ROOT_DIR/infra/bootstrap"
AGENT_DIR="$ROOT_DIR/agents/akto-demo-agent"

VERSION="${1:-build-$(date -u +%Y%m%d%H%M%S)}"
REGION="${AWS_REGION:-us-east-1}"

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

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
echo "Creates one HTTP Gateway, one Runtime, one MCP Gateway, two MCP targets,"
echo "the Runtime image repository, and least-privilege IAM."
echo

if ! confirm "Continue?"; then
  echo "Aborted."
  exit 0
fi

bold "=== terraform init ==="
terraform -chdir="$TF_DIR" init -backend-config=backend.hcl

bold "=== create ECR repository ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_VARS[@]}" \
  -target=module.demo_agent.aws_ecr_repository.this

REPO_URL="$(terraform -chdir="$TF_DIR" output -raw demo_agent_ecr_repository_url)"
if [ -z "$REPO_URL" ]; then
  echo "Could not read demo_agent_ecr_repository_url." >&2
  exit 1
fi

REGISTRY="${REPO_URL%%/*}"
bold "=== build and push $REPO_URL:$VERSION ==="
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 -t "${REPO_URL}:${VERSION}" --push "$AGENT_DIR"

bold "=== deploy complete topology ==="
terraform -chdir="$TF_DIR" apply "${TF_VARS[@]}"

bold "=== done ==="
echo "HTTP Gateway:  $(terraform -chdir="$TF_DIR" output -raw http_gateway_url)"
echo "HTTP target:   $(terraform -chdir="$TF_DIR" output -raw http_gateway_target_name)"
echo "Agent Runtime: $(terraform -chdir="$TF_DIR" output -raw demo_agent_runtime_arn)"
echo "MCP Gateway:   $(terraform -chdir="$TF_DIR" output -raw mcp_gateway_url)"
echo
echo "Ask it:"
echo "  scripts/invoke.sh \"What does API security testing cover?\""
echo "Smoke test:"
echo "  scripts/smoke-test.sh"
