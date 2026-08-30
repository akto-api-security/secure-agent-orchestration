#!/usr/bin/env bash
# Tears down the deployed stack in infra/environments/dev.
#
# None of the 4 ECR repositories have force_delete enabled, and Terraform
# can't delete a repository that still holds images -- so this clears each
# one first (using the real repo names from `terraform output`, not a
# guess, so it works regardless of your project_name/environment), then
# runs `terraform destroy` for everything else.
#
# Leaves the Terraform state backend (infra/bootstrap) untouched -- see
# README.md, "Tearing it down" for removing that too. That's a separate,
# rarer, higher-stakes step (it empties and deletes the bucket holding this
# very deployment's state) and isn't automated here on purpose.
#
# Usage: scripts/destroy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/dev"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

tf_output() {
  terraform -chdir="$TF_DIR" output -raw "$1" 2>/dev/null || true
}

REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || echo us-east-1)}"

bold "=== This will destroy the deployed stack in infra/environments/dev ==="
echo "That's: all 4 ECR repositories (images included), both AgentCore"
echo "Runtimes, the Orchestrator, the Approval Agent, the Gateway, the"
echo "interceptor Lambda, the DynamoDB table, all IAM roles/policies, and"
echo "the KMS grants key (scheduled for deletion, not removed immediately --"
echo "see the note at the end)."
echo "The Terraform state backend (infra/bootstrap) is NOT touched."
echo

if ! confirm "Continue?"; then
  echo "Aborted."
  exit 0
fi

bold "=== Clearing ECR repositories (force_delete isn't enabled) ==="
for output in orchestrator_ecr_repository_url api_security_agent_ecr_repository_url \
              agentic_security_agent_ecr_repository_url approval_agent_ecr_repository_url; do
  repo_url="$(tf_output "$output")"
  if [ -z "$repo_url" ]; then
    echo "Skipping $output -- not resolved (already destroyed, or never applied)."
    continue
  fi
  repo_name="${repo_url##*/}"
  echo "Deleting $repo_name (region $REGION)..."
  aws ecr delete-repository --repository-name "$repo_name" --region "$REGION" --force >/dev/null 2>&1 \
    && echo "  deleted." \
    || echo "  already gone or couldn't delete -- terraform destroy below will report if this blocks anything."
done

bold "=== terraform destroy ==="
(cd "$TF_DIR" && terraform destroy)

bold "=== Done ==="
echo "Note: the KMS grants key is now \"Pending deletion\" for 7 days (AWS's"
echo "mandatory minimum window for key deletion), not gone immediately --"
echo "this is expected, not a stuck destroy."
