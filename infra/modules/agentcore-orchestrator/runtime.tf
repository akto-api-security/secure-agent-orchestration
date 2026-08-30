# protocol_configuration.server_protocol = "HTTP" (not "A2A"): the
# orchestrator is the top-level entry point invoked directly by a caller,
# never as an A2A peer -- see agents/orchestrator/README.md for the full
# reasoning. "HTTP" is a documented value alongside "MCP" and "A2A" per
# AWS's ProtocolConfiguration API reference.
#
# No authorizer_configuration block, matching Phase 2's agents: inbound
# authorization defaults to AWS_IAM (SigV4), tested the same way as the
# Phase 2 agents (a SigV4-signed InvokeAgentRuntime call).
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
    API_SECURITY_AGENT_RUNTIME_ARN     = var.api_security_agent_runtime_arn
    AGENTIC_SECURITY_AGENT_RUNTIME_ARN = var.agentic_security_agent_runtime_arn
    APPROVAL_AGENT_RUNTIME_ARN         = var.approval_agent_runtime_arn
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
