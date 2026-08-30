locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Defined before the interceptor module below since the interceptor needs
# its runtime ARN to call it; the Approval Agent has no dependency back on
# the interceptor or gateway, so this ordering avoids a circular module
# reference.
module "approval_agent" {
  source = "../../modules/approval-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_runtime_name = "asl_approval_agent_${var.environment}"
  description        = "Approval Agent -- owns deterministic approval and semantic HITL decisions, human decision state, and signed authorization grants for the REQUEST interceptor."

  container_image_tag = var.image_tag

  tags = local.common_tags
}

# Defined before the gateway module below since the gateway needs its ARN
# (to add an interceptor_configuration block + an IAM permission on its own
# service role) -- the interceptor itself has no dependency back on the
# gateway, so this ordering avoids a circular module reference.
module "gateway_interceptor" {
  source = "../../modules/gateway-interceptor"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  log_level    = var.interceptor_log_level

  # Routes every OPA-allowed tools/call to the Approval Agent for
  # the authorization decision (see interceptor/handler.py).
  approval_agent_runtime_arn = module.approval_agent.agent_runtime_arn

  tags = local.common_tags
}

module "agentcore_gateway" {
  source = "../../modules/agentcore-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  enable_interceptor     = true
  interceptor_lambda_arn = module.gateway_interceptor.lambda_arn

  tags = local.common_tags
}

# Same module instantiated twice -- the two agents differ only in name,
# description, and which target prefix they discover tools from.
module "api_security_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "api-security-agent"
  agent_runtime_name = "asl_api_security_agent_${var.environment}"
  description        = "API Security Agent -- receives A2A tasks about API security and DAST, and answers them via the Akto API Security MCP target through the Gateway."

  gateway_arn       = module.agentcore_gateway.gateway_arn
  gateway_url       = module.agentcore_gateway.gateway_url
  mcp_target_prefix = "mac-akto-api-mcp"

  container_image_tag = var.image_tag

  tags = local.common_tags
}

module "agentic_security_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "agentic-security-agent"
  agent_runtime_name = "asl_agentic_security_agent_${var.environment}"
  description        = "Agentic Security Agent -- receives A2A tasks about Atlas, Argus, agentic security, MCP security, and A2A security, and answers them via the Akto Agentic Security MCP target through the Gateway."

  gateway_arn       = module.agentcore_gateway.gateway_arn
  gateway_url       = module.agentcore_gateway.gateway_url
  mcp_target_prefix = "mac-akto-ai-mcp"

  container_image_tag = var.image_tag

  tags = local.common_tags
}

# Never talks to the Gateway directly -- only the two delegated agents
# above and the Approval Agent, over A2A/InvokeAgentRuntime.
module "orchestrator" {
  source = "../../modules/agentcore-orchestrator"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_runtime_name = "asl_orchestrator_${var.environment}"
  description        = "Orchestrator Agent -- entry point for user questions; routes to the API Security Agent or Agentic Security Agent over A2A based on a deterministic keyword match."

  api_security_agent_runtime_arn     = module.api_security_agent.agent_runtime_arn
  agentic_security_agent_runtime_arn = module.agentic_security_agent.agent_runtime_arn
  # Resumes a paused delegated-agent task by checking what a human
  # decided (read-only get_decision calls -- see approval_client.py).
  approval_agent_runtime_arn = module.approval_agent.agent_runtime_arn

  container_image_tag = var.image_tag

  tags = local.common_tags
}
