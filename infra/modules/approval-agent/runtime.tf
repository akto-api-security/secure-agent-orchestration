# protocol_configuration.server_protocol = "HTTP", same reasoning as the
# Orchestrator (Phase 3): the Approval Agent is called directly by the
# interceptor Lambda and by the orchestrator/human CLI -- never as an A2A
# peer -- so a plain structured JSON request/response over the HTTP
# protocol contract is all it needs (no agent card, no A2A message
# envelope). Confirmed AWS capability, not an inference: this is the exact
# same protocol/invocation mechanism already live-tested for the
# Orchestrator.
#
# No authorizer_configuration block: inbound authorization defaults to
# AWS_IAM (SigV4), matching every other AgentCore Runtime resource in this
# project.
resource "aws_bedrockagentcore_agent_runtime" "this" {
  agent_runtime_name = var.agent_runtime_name
  description        = var.description
  role_arn           = aws_iam_role.execution.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.this.repository_url}:${var.container_image_tag}"
    }
  }

  environment_variables = {
    APPROVAL_STATE_TABLE         = aws_dynamodb_table.approval_state.name
    GRANT_KMS_KEY_ID             = aws_kms_key.grants.arn
    BEDROCK_MODEL_ID             = var.model_id
    APPROVAL_PENDING_TTL_SECONDS = tostring(var.approval_pending_ttl_seconds)
    GRANT_TTL_SECONDS            = tostring(var.grant_ttl_seconds)
    LOG_LEVEL                    = var.log_level
    # Not AWS_REGION -- reserved by the AgentCore Runtime platform itself
    # (same reasoning as GATEWAY_REGION in Phase 2's gateway_tool.py).
    AGENT_REGION = var.aws_region
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = "HTTP"
  }

  tags = var.tags
}
