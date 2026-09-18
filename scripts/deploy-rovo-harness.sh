#!/usr/bin/env bash
# Create or update the Rovo demo AgentCore Harness (CLI path, no Terraform state needed).
# Usage: scripts/deploy-rovo-harness.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TF_DIR="$SCRIPT_DIR/../infra/environments/akto-demo"
REGION="${AWS_REGION:-us-east-1}"
HARNESS_NAME="asl_rovo_harness_demo"
HARNESS_ROLE="${HARNESS_EXECUTION_ROLE_ARN:-arn:aws:iam::887089841930:role/service-role/AmazonBedrockAgentCoreHarnessDefaultServiceRole-edend}"

GATEWAY_ARN="${MCP_GATEWAY_ARN:-}"
if [ -z "$GATEWAY_ARN" ] && [ -f "$TF_DIR/backend.hcl" ]; then
  GATEWAY_ARN="$(terraform -chdir="$TF_DIR" output -raw mcp_gateway_arn 2>/dev/null || true)"
fi
GATEWAY_ARN="${GATEWAY_ARN:-arn:aws:bedrock-agentcore:us-east-1:887089841930:gateway/asl-gateway-demo-9lzr1onrx9}"

SYSTEM_PROMPT='You are a backlog organization assistant for Jira and Confluence. Use read_uploaded_document when the user references an uploaded guide. Use search_jira_tickets and search_confluence_pages to gather context. Use open_url only when explicitly required. If a tool call is blocked by policy, say so and stop.'

TOOLS="$(python3 -c "import json; print(json.dumps([{'type':'agentcore_gateway','name':'demo-guardrails-mcp','config':{'agentCoreGateway':{'gatewayArn':'${GATEWAY_ARN}','outboundAuth':{'awsIam':{}}}}}]))")"
MODEL='{"bedrockModelConfig":{"modelId":"us.anthropic.claude-haiku-4-5-20251001-v1:0"}}'
PROMPT_JSON="$(python3 -c "import json; print(json.dumps([{'text': '''$SYSTEM_PROMPT'''}]))")"

EXISTING_ID="$(aws bedrock-agentcore-control list-harnesses --region "$REGION" \
  --query "harnesses[?harnessName=='${HARNESS_NAME}'].harnessId | [0]" --output text 2>/dev/null || true)"

# Tool name must match the MCP gateway target prefix (demo-guardrails-mcp), not the gateway ID.
MEMORY='{"optionalValue":{"disabled":{}}}'

if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "None" ]; then
  echo "Updating harness ${EXISTING_ID}"
  aws bedrock-agentcore-control update-harness \
    --harness-id "$EXISTING_ID" \
    --region "$REGION" \
    --system-prompt "$PROMPT_JSON" \
    --allowed-tools '["@demo-guardrails-mcp/*"]' \
    --tools "$TOOLS" \
    --memory "$MEMORY" \
    --max-iterations 20 \
    --timeout-seconds 900 >/dev/null
  HARNESS_ID="$EXISTING_ID"
else
  echo "Creating harness ${HARNESS_NAME}"
  HARNESS_ID="$(aws bedrock-agentcore-control create-harness \
    --region "$REGION" \
    --harness-name "$HARNESS_NAME" \
    --execution-role-arn "$HARNESS_ROLE" \
    --model "$MODEL" \
    --system-prompt "$PROMPT_JSON" \
    --allowed-tools '["@demo-guardrails-mcp/*"]' \
    --tools "$TOOLS" \
    --memory '{"disabled":{}}' \
    --max-iterations 20 \
    --timeout-seconds 900 \
    --query harness.harnessId --output text)"
fi

HARNESS_ARN="$(aws bedrock-agentcore-control get-harness --harness-id "$HARNESS_ID" --region "$REGION" --query harness.arn --output text)"
echo "Harness ARN: ${HARNESS_ARN}"
echo
echo "Ensure the harness execution role can InvokeGateway on the MCP gateway,"
echo "and the gateway resource policy allows that role (see docs in agents/rovo-demo-agent/README.md)."
echo
echo "Test:"
echo "  export ROVO_HARNESS_ARN=\"${HARNESS_ARN}\""
echo "  scripts/invoke-rovo-harness.py \"I uploaded a Backlog Guide. Organize my Jira backlog.\""
