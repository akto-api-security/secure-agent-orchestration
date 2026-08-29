# No authorizer_configuration block: omitting it leaves inbound A2A
# authorization on AWS_IAM (SigV4) rather than requiring a CUSTOM_JWT
# authorizer, which would mean standing up Cognito. This mirrors the Phase 1
# Gateway's own inbound-auth decision and its reasoning (reuse the AWS
# identities already in use, avoid Cognito infrastructure with no other
# consumer, and stay directly testable with SigV4-signed requests).
#
# This is an implementation inference, not a directly-quoted AWS default: it
# follows from the provider schema (authorizer_configuration is optional and
# only configures a *JWT* authorizer) plus AWS's A2A protocol-contract docs,
# which describe SigV4 as a first-class, non-JWT auth mode and document a
# distinct 403 response shape for "SigV4-configured agents". Verify with a
# real signed invoke before treating it as final -- see the agent's README.
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
    server_protocol = "A2A"
  }

  tags = var.tags
}
