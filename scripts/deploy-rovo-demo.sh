#!/usr/bin/env bash
# Deploy Rovo demo: MCP server, Runtime+Gateway, and Harness.
# Usage: scripts/deploy-rovo-demo.sh [image-tag]
# Requires: AWS_PROFILE, AWS_REGION, AUTO_APPROVE=1 optional
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/akto-demo"
ROVO_AGENT_DIR="$ROOT_DIR/agents/rovo-demo-agent"
ENDPOINT_FILE="$ROOT_DIR/examples/demo-guardrails-mcp/.endpoint"

REGION="${AWS_REGION:-us-east-1}"
VERSION="${1:-build-$(date -u +%Y%m%d%H%M%S)}"
EXTERNAL_RUNTIME_ARN="${EXTERNAL_RUNTIME_ARN:-arn:aws:bedrock-agentcore:us-east-1:887089841930:runtime/asl_demo_agent_demo-od6tc17ZSs}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }

APPROVE_FLAG=()
[ -n "${AUTO_APPROVE:-}" ] && APPROVE_FLAG=(-auto-approve)

TF_VARS=(
  -var="image_tag=${VERSION}"
  -var="rovo_image_tag=${VERSION}"
  -var="aws_region=${REGION}"
  -var="create_container_runtime=false"
  -var="create_rovo_runtime=true"
  -var="create_rovo_harness=true"
  -var="external_runtime_arn=${EXTERNAL_RUNTIME_ARN}"
)

bold "=== 1/4 demo-guardrails-mcp (App Runner) ==="
AUTO_APPROVE=1 "${SCRIPT_DIR}/deploy-demo-mcp.sh" latest

MCP_ENDPOINT="$(tr -d '[:space:]' < "$ENDPOINT_FILE")"
TF_VARS+=(-var="demo_guardrails_mcp_endpoint=${MCP_ENDPOINT}")

bold "=== 2/4 terraform init ==="
terraform -chdir="$TF_DIR" init -backend-config=backend.hcl

bold "=== 3/4 rovo ECR + image push ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_VARS[@]}" \
  "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}" \
  -target=module.rovo_demo_agent.aws_ecr_repository.this

ROVO_REPO="$(terraform -chdir="$TF_DIR" output -raw rovo_demo_agent_ecr_repository_url)"
REGISTRY="${ROVO_REPO%%/*}"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY"
docker buildx build --platform linux/arm64 -t "${ROVO_REPO}:${VERSION}" --push "$ROVO_AGENT_DIR"

bold "=== 4/4 apply rovo runtime, gateway, harness ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_VARS[@]}" \
  "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}" \
  -target=module.rovo_demo_agent \
  -target=module.rovo_http_gateway \
  -target=module.rovo_harness

bold "=== done ==="
echo "Rovo Runtime:  $(terraform -chdir="$TF_DIR" output -raw rovo_demo_agent_runtime_arn)"
echo "Rovo Gateway:  $(terraform -chdir="$TF_DIR" output -raw rovo_http_gateway_url)"
echo "Rovo Harness:  $(terraform -chdir="$TF_DIR" output -raw rovo_harness_arn)"
echo
echo "Test runtime:"
echo "  scripts/invoke-rovo-demo.sh \"I uploaded a Backlog Guide. Organize my Jira backlog.\""
echo "Test harness:"
echo "  export ROVO_HARNESS_ARN=\"\$(terraform -chdir=$TF_DIR output -raw rovo_harness_arn)\""
echo "  scripts/invoke-rovo-harness.py \"I uploaded a Backlog Guide. Organize my Jira backlog.\""
