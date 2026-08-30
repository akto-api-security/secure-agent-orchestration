#!/usr/bin/env bash
# Step 1 of a fresh customer deployment: create the Terraform
# state backend (infra/bootstrap) and generate the partial backend config
# infra/environments/dev needs (see infra/environments/dev/backend.tf,
# which deliberately has no literal bucket/region -- Terraform backend
# blocks can never reference variables, so this is supplied at `terraform
# init` time instead).
#
# This script only prints the terraform/init commands it wants to run and
# asks for confirmation before running the two that touch AWS
# (bootstrap's own init/apply) -- nothing here silently applies infra.
#
# Usage: scripts/bootstrap.sh [aws_region] [project_name]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_DIR="$SCRIPT_DIR/../infra/bootstrap"
DEV_DIR="$SCRIPT_DIR/../infra/environments/dev"

AWS_REGION="${1:-us-east-1}"
PROJECT_NAME="${2:-agent-security-lab}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

bold "=== Step 1: Terraform state backend (infra/bootstrap) ==="
echo "This will create one S3 bucket in region $AWS_REGION to hold this"
echo "deployment's Terraform state (versioned, SSE-KMS encrypted, public"
echo "access blocked). Project name prefix: $PROJECT_NAME"
echo

if ! confirm "Run 'terraform init && terraform apply' in $BOOTSTRAP_DIR now?"; then
  echo "Skipped. Run manually when ready:"
  echo "  cd $BOOTSTRAP_DIR && terraform init && terraform apply -var=\"aws_region=$AWS_REGION\" -var=\"project_name=$PROJECT_NAME\""
  exit 0
fi

(cd "$BOOTSTRAP_DIR" && terraform init && terraform apply -var="aws_region=$AWS_REGION" -var="project_name=$PROJECT_NAME")

STATE_BUCKET="$(cd "$BOOTSTRAP_DIR" && terraform output -raw state_bucket_name)"
if [ -z "$STATE_BUCKET" ]; then
  echo "Could not read state_bucket_name from infra/bootstrap's output -- aborting." >&2
  exit 1
fi

bold "=== Step 2: generate infra/environments/dev/backend.hcl ==="
cat > "$DEV_DIR/backend.hcl" <<EOF
bucket = "$STATE_BUCKET"
region = "$AWS_REGION"
EOF
echo "Wrote $DEV_DIR/backend.hcl (gitignored -- account-specific, not shared)."

bold "=== Next step ==="
echo "Initialize the dev environment against this backend:"
echo "  cd $DEV_DIR && terraform init -backend-config=backend.hcl"
echo
echo "(If this re-points an existing environment at the same bucket/key,"
echo "add -reconfigure -- it won't move or touch any state.)"
