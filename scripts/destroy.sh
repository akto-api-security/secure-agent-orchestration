#!/usr/bin/env bash
# Destroy the topology while leaving the Terraform state bucket intact.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/akto-demo"
REGION="${AWS_REGION:-us-east-1}"

APPROVE_FLAG=()
if [ -n "${AUTO_APPROVE:-}" ]; then
  APPROVE_FLAG=(-auto-approve)
else
  read -r -p "Destroy the AgentCore topology? [y/N] " reply
  if [[ ! "$reply" =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
  fi
fi

REPO_URL="$(terraform -chdir="$TF_DIR" output -raw demo_agent_ecr_repository_url 2>/dev/null || true)"
if [ -n "$REPO_URL" ]; then
  aws ecr delete-repository \
    --repository-name "${REPO_URL##*/}" \
    --region "$REGION" \
    --force >/dev/null 2>&1 || true
fi

terraform -chdir="$TF_DIR" destroy "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}"
