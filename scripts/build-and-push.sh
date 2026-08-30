#!/usr/bin/env bash
# Build and push all 4 service images (ARM64, per AgentCore Runtime's
# requirement) to this deployment's own per-service ECR repositories,
# tagged with one immutable version instead of "latest" -- Terraform
# doesn't detect a re-pushed image under the same tag, so a rebuild under
# ":latest" can silently go stale.
#
# Requires: infra/environments/dev already applied at least once (so each
# service's *_ecr_repository_url output exists), Docker with buildx,
# authenticated AWS CLI.
#
# Usage: scripts/build-and-push.sh [version]
#   version defaults to the current git short SHA.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/dev"

VERSION="${1:-$(git -C "$ROOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "manual-$(date +%Y%m%d%H%M%S)")}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }

tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

# service_key : dockerfile_dir : terraform_output_name
SERVICES=(
  "orchestrator:$ROOT_DIR/agents/orchestrator:orchestrator_ecr_repository_url"
  "api-security-agent:$ROOT_DIR/agents/api-security-agent:api_security_agent_ecr_repository_url"
  "agentic-security-agent:$ROOT_DIR/agents/agentic-security-agent:agentic_security_agent_ecr_repository_url"
  "approval-agent:$ROOT_DIR/approval-agent:approval_agent_ecr_repository_url"
)

REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"
LOGGED_IN_REGISTRIES=()

ecr_login_once() {
  local registry="$1"
  for r in "${LOGGED_IN_REGISTRIES[@]:-}"; do
    [ "$r" = "$registry" ] && return
  done
  aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$registry"
  LOGGED_IN_REGISTRIES+=("$registry")
}

bold "=== Building and pushing version: $VERSION ==="
PINNED_VARS=()

for entry in "${SERVICES[@]}"; do
  IFS=":" read -r key dir output_name <<< "$entry"

  repo_url="$(tf_output "$output_name")"
  if [ -z "$repo_url" ]; then
    echo "Could not resolve $output_name from 'terraform output' in $TF_DIR." >&2
    echo "Has 'terraform apply' created the $key ECR repository yet?" >&2
    exit 1
  fi

  registry="${repo_url%%/*}"
  ecr_login_once "$registry"

  bold "--- $key ($dir) -> $repo_url:$VERSION ---"
  docker buildx build --platform linux/arm64 -t "${repo_url}:${VERSION}" --push "$dir"

  PINNED_VARS+=("$key -> image_tag=$VERSION")
done

bold "=== Done ==="
echo "All 4 images pushed as :$VERSION. Deploy them with:"
echo "  cd $TF_DIR && terraform apply -var=\"image_tag=$VERSION\""
echo
echo "(All 4 services share one image_tag value by design -- see"
echo "infra/environments/dev/variables.tf.)"
