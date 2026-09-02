# Omitting authorizer_configuration leaves inbound Runtime authorization on
# AWS IAM. The outer Gateway signs Runtime requests with its service role.
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
    GATEWAY_URL       = var.gateway_url
    GATEWAY_REGION    = var.aws_region
    MCP_TARGET_PREFIX = var.mcp_target_prefix
    BEDROCK_MODEL_ID  = var.model_id
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  protocol_configuration {
    server_protocol = var.server_protocol
  }

  tags = var.tags
}
