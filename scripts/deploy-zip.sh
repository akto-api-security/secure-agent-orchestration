#!/usr/bin/env bash
# Deploy Client -> HTTP Gateway -> Runtime -> MCP Gateway using the prebuilt zip.
# Skips Docker/ECR image build (minutes faster than scripts/deploy.sh).
#
# Usage: scripts/deploy-zip.sh
# Set AUTO_APPROVE=1 to skip prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
TF_DIR="$ROOT_DIR/infra/environments/akto-demo"
BOOTSTRAP_DIR="$ROOT_DIR/infra/bootstrap"
ZIP_PATH="$ROOT_DIR/agents/akto-demo-agent/deployment_package.zip"

REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-demo}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  [ -n "${AUTO_APPROVE:-}" ] && return 0
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

APPROVE_FLAG=()
[ -n "${AUTO_APPROVE:-}" ] && APPROVE_FLAG=(-auto-approve)

if [ ! -f "$ZIP_PATH" ]; then
  echo "Missing $ZIP_PATH" >&2
  exit 1
fi

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
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
CODE_BUCKET="${CODE_BUCKET:-asl-demo-agent-code-${ACCOUNT_ID}-${REGION}}"
ZIP_KEY="${ZIP_KEY:-asl-demo-agent-demo/deployment_package.zip}"
RUNTIME_NAME="asl_demo_agent_${ENVIRONMENT}"
EXEC_ROLE_NAME="asl-demo-agent-execution-${ENVIRONMENT}"
MODEL_ID="${BEDROCK_MODEL_ID:-us.anthropic.claude-haiku-4-5-20251001-v1:0}"

TF_BASE=(
  -var="aws_region=${REGION}"
  -var="create_container_runtime=false"
)

bold "=== AgentCore zip deploy ==="
echo "Account: $ACCOUNT_ID | Region: $REGION"
echo "Zip: $ZIP_PATH"
echo

if ! confirm "Deploy MCP Gateway + IAM (no Docker build)?"; then
  echo "Aborted."
  exit 0
fi

bold "=== terraform init ==="
terraform -chdir="$TF_DIR" init -backend-config=backend.hcl

bold "=== terraform: MCP Gateway + agent IAM/ECR (no Runtime) ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_BASE[@]}" \
  "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}" \
  -target=module.mcp_gateway \
  -target=module.demo_agent

MCP_GATEWAY_URL="$(terraform -chdir="$TF_DIR" output -raw mcp_gateway_url)"
EXEC_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${EXEC_ROLE_NAME}"

bold "=== upload zip to s3://${CODE_BUCKET}/${ZIP_KEY} ==="
if ! aws s3api head-bucket --bucket "$CODE_BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$CODE_BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$CODE_BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=${REGION}"
  fi
  aws s3api put-public-access-block \
    --bucket "$CODE_BUCKET" \
    --public-access-block-configuration \
      BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
fi

aws s3 cp "$ZIP_PATH" "s3://${CODE_BUCKET}/${ZIP_KEY}" --region "$REGION"

bold "=== grant execution role S3 read on zip ==="
aws iam put-role-policy \
  --role-name "$EXEC_ROLE_NAME" \
  --policy-name S3CodeAccess \
  --policy-document "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Action\": [\"s3:GetObject\", \"s3:GetObjectVersion\"],
      \"Resource\": \"arn:aws:s3:::${CODE_BUCKET}/${ZIP_KEY}\"
    }]
  }"

bold "=== create AgentCore Runtime from zip ==="
RUNTIME_ARN=""
if aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$RUNTIME_NAME" \
  --region "$REGION" >/dev/null 2>&1; then
  RUNTIME_ARN="$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_NAME" \
    --region "$REGION" \
    --query agentRuntimeArn --output text)"
  echo "Runtime already exists: $RUNTIME_ARN"
else
  CREATE_OUT="$(aws bedrock-agentcore-control create-agent-runtime \
    --region "$REGION" \
    --agent-runtime-name "$RUNTIME_NAME" \
    --role-arn "$EXEC_ROLE_ARN" \
    --description "Demo agent from zip" \
    --network-configuration '{"networkMode":"PUBLIC"}' \
    --protocol-configuration '{"serverProtocol":"HTTP"}' \
    --environment-variables "{
      \"GATEWAY_URL\": \"${MCP_GATEWAY_URL}\",
      \"GATEWAY_REGION\": \"${REGION}\",
      \"MCP_TARGET_PREFIX\": \"mac-akto-api-mcp\",
      \"BEDROCK_MODEL_ID\": \"${MODEL_ID}\"
    }" \
    --agent-runtime-artifact "{
      \"codeConfiguration\": {
        \"code\": {
          \"s3\": {
            \"bucket\": \"${CODE_BUCKET}\",
            \"prefix\": \"${ZIP_KEY}\"
          }
        },
        \"runtime\": \"PYTHON_3_12\",
        \"entryPoint\": [\"main.py\"]
      }
    }")"
  RUNTIME_ARN="$(printf '%s' "$CREATE_OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["agentRuntimeArn"])')"
  echo "Created runtime: $RUNTIME_ARN"
fi

bold "=== wait for Runtime READY ==="
RUNTIME_ID="${RUNTIME_ID:-}"
if [ -z "$RUNTIME_ID" ] && [ -n "$RUNTIME_ARN" ]; then
  RUNTIME_ID="${RUNTIME_ARN##*/}"
fi
for _ in $(seq 1 60); do
  STATUS="$(aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "${RUNTIME_ID:-$RUNTIME_NAME}" \
    --region "$REGION" \
    --query status --output text 2>/dev/null || echo UNKNOWN)"
  echo "  status: $STATUS"
  if [ "$STATUS" = "READY" ]; then
    break
  fi
  if [ "$STATUS" = "CREATE_FAILED" ] || [ "$STATUS" = "UPDATE_FAILED" ]; then
    echo "Runtime failed with status $STATUS" >&2
    exit 1
  fi
  sleep 10
done

bold "=== terraform: HTTP Gateway + Runtime resource policy ==="
terraform -chdir="$TF_DIR" apply \
  "${TF_BASE[@]}" \
  -var="external_runtime_arn=${RUNTIME_ARN}" \
  "${APPROVE_FLAG[@]+"${APPROVE_FLAG[@]}"}" \
  -target=module.http_gateway

bold "=== done ==="
echo "HTTP Gateway:  $(terraform -chdir="$TF_DIR" output -raw http_gateway_url)"
echo "HTTP target:   $(terraform -chdir="$TF_DIR" output -raw http_gateway_target_name)"
echo "Agent Runtime: ${RUNTIME_ARN}"
echo "MCP Gateway:   $(terraform -chdir="$TF_DIR" output -raw mcp_gateway_url)"
echo
echo "Ask it:"
echo "  export AGENT_RUNTIME_ARN=\"${RUNTIME_ARN}\""
echo "  scripts/invoke.sh \"What does API security testing cover?\""
