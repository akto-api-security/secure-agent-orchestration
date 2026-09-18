#!/usr/bin/env bash
# Build and deploy examples/demo-guardrails-mcp to AWS App Runner (HTTPS).
#
# Creates (once): ECR repo, App Runner ECR access role, App Runner service.
# Writes the public MCP endpoint to examples/demo-guardrails-mcp/.endpoint
#
# Usage: scripts/deploy-demo-mcp-server.sh [image-tag]
# Set AUTO_APPROVE=1 to skip prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR/.."
MCP_DIR="$ROOT_DIR/examples/demo-guardrails-mcp"
ENDPOINT_FILE="$MCP_DIR/.endpoint"

REGION="${AWS_REGION:-us-east-1}"
ENVIRONMENT="${ENVIRONMENT:-demo}"
IMAGE_TAG="${1:-latest}"
SERVICE_NAME="asl-demo-guardrails-mcp-${ENVIRONMENT}"
ECR_REPO="asl-demo-guardrails-mcp"
ECR_ROLE="asl-apprunner-${ECR_REPO}-ecr-access"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
confirm() {
  [ -n "${AUTO_APPROVE:-}" ] && return 0
  read -r -p "$1 [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]]
}

if ! confirm "Build and deploy demo MCP server to App Runner in ${REGION}?"; then
  echo "Aborted."
  exit 0
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
REPO_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"
IMAGE="${REPO_URI}:${IMAGE_TAG}"

bold "=== ECR repository ==="
if ! aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$REGION" >/dev/null 2>&1; then
  aws ecr create-repository \
    --repository-name "$ECR_REPO" \
    --image-scanning-configuration scanOnPush=true \
    --region "$REGION" >/dev/null
  echo "Created ${ECR_REPO}"
else
  echo "Using existing ${ECR_REPO}"
fi

if [ "${SKIP_BUILD:-}" = "1" ]; then
  bold "=== skip build (SKIP_BUILD=1) — using ${IMAGE} ==="
  if ! aws ecr describe-images --repository-name "$ECR_REPO" --image-ids "imageTag=${IMAGE_TAG}" \
    --region "$REGION" >/dev/null 2>&1; then
    echo "Image ${IMAGE} not found in ECR. Build and push first, or unset SKIP_BUILD." >&2
    exit 1
  fi
else
  bold "=== build and push ${IMAGE} ==="
  echo "App Runner needs linux/amd64. On Apple Silicon this uses QEMU and can take a few minutes."
  echo "To build yourself and skip this step:"
  echo "  aws ecr get-login-password --region ${REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
  echo "  docker buildx build --platform linux/amd64 --progress=plain -t ${IMAGE} -f ${MCP_DIR}/Dockerfile ${MCP_DIR} --push"
  echo "  SKIP_BUILD=1 scripts/deploy-demo-mcp-server.sh"
  aws ecr get-login-password --region "$REGION" \
    | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
  docker buildx build \
    --platform linux/amd64 \
    --progress=plain \
    -t "$IMAGE" \
    -f "${MCP_DIR}/Dockerfile" \
    "$MCP_DIR" \
    --push
fi

bold "=== App Runner ECR access role ==="
if ! aws iam get-role --role-name "$ECR_ROLE" >/dev/null 2>&1; then
  ECR_ROLE_ARN="$(aws iam create-role --role-name "$ECR_ROLE" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }' --query Role.Arn --output text)"
  aws iam attach-role-policy --role-name "$ECR_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess
  echo "Created ${ECR_ROLE}; waiting for IAM propagation..."
  sleep 15
else
  ECR_ROLE_ARN="$(aws iam get-role --role-name "$ECR_ROLE" --query Role.Arn --output text)"
  echo "Using existing ${ECR_ROLE}"
fi

SOURCE_CONFIG="$(python3 - <<EOF
import json
print(json.dumps({
    "AuthenticationConfiguration": {"AccessRoleArn": "${ECR_ROLE_ARN}"},
    "AutoDeploymentsEnabled": False,
    "ImageRepository": {
        "ImageIdentifier": "${IMAGE}",
        "ImageRepositoryType": "ECR",
        "ImageConfiguration": {"Port": "8080"},
    },
}))
EOF
)"

INSTANCE_CONFIG='{"Cpu":"256","Memory":"512"}'

bold "=== App Runner service ${SERVICE_NAME} ==="
SERVICE_ARN="$(aws apprunner list-services --region "$REGION" \
  --query "ServiceSummaryList[?ServiceName=='${SERVICE_NAME}'].ServiceArn | [0]" --output text)"

if [ -z "$SERVICE_ARN" ] || [ "$SERVICE_ARN" = "None" ]; then
  SERVICE_ARN="$(aws apprunner create-service \
    --service-name "$SERVICE_NAME" \
    --source-configuration "$SOURCE_CONFIG" \
    --instance-configuration "$INSTANCE_CONFIG" \
    --region "$REGION" \
    --query Service.ServiceArn --output text)"
  echo "Created service"
else
  aws apprunner update-service \
    --service-arn "$SERVICE_ARN" \
    --source-configuration "$SOURCE_CONFIG" \
    --instance-configuration "$INSTANCE_CONFIG" \
    --region "$REGION" >/dev/null
  echo "Updated service"
fi

bold "=== wait for RUNNING ==="
for _ in $(seq 1 60); do
  STATUS="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" \
    --query 'Service.Status' --output text)"
  echo "  status: ${STATUS}"
  if [ "$STATUS" = "RUNNING" ]; then
    break
  fi
  if [ "$STATUS" = "CREATE_FAILED" ] || [ "$STATUS" = "DELETE_FAILED" ]; then
    echo "App Runner service failed: ${STATUS}" >&2
    exit 1
  fi
  sleep 10
done

SERVICE_URL="$(aws apprunner describe-service --service-arn "$SERVICE_ARN" --region "$REGION" \
  --query 'Service.ServiceUrl' --output text)"
if [[ "$SERVICE_URL" != https://* ]]; then
  SERVICE_URL="https://${SERVICE_URL}"
fi
MCP_ENDPOINT="${SERVICE_URL%/}/mcp"
printf '%s\n' "$MCP_ENDPOINT" > "$ENDPOINT_FILE"

bold "=== done ==="
echo "App Runner URL:  ${SERVICE_URL}"
echo "MCP endpoint:    ${MCP_ENDPOINT}"
echo "Saved to:        ${ENDPOINT_FILE}"
echo
echo "Next: scripts/register-demo-mcp-target.sh"
