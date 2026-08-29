# Phase 1 resources live here via infra/modules/. Later phases (delegated
# agents, orchestrator, interceptor/OPA, approval-workflow) will add their
# own module blocks below as they're implemented.

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "agentcore_gateway" {
  source = "../../modules/agentcore-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  tags = merge(local.common_tags, {
    Phase = "1"
  })
}

# Phase 2: delegated AgentCore Runtime agents, each invoking the Phase 1
# gateway above and scoped to one of its two MCP targets. Same module,
# instantiated twice -- the two agents differ only in name, description,
# and which target prefix they discover tools from.
module "api_security_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "api-security-agent"
  agent_runtime_name = "asl_api_security_agent_${var.environment}"
  description        = "API Security Agent -- receives A2A tasks about API security and DAST, and answers them via the Akto API Security MCP target through the Phase 1 Gateway."

  gateway_arn       = module.agentcore_gateway.gateway_arn
  gateway_url       = module.agentcore_gateway.gateway_url
  mcp_target_prefix = "mac-akto-api-mcp"

  tags = merge(local.common_tags, {
    Phase = "2"
  })
}

module "agentic_security_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "agentic-security-agent"
  agent_runtime_name = "asl_agentic_security_agent_${var.environment}"
  description        = "Agentic Security Agent -- receives A2A tasks about Atlas, Argus, agentic security, MCP security, and A2A security, and answers them via the Akto Agentic Security MCP target through the Phase 1 Gateway."

  gateway_arn       = module.agentcore_gateway.gateway_arn
  gateway_url       = module.agentcore_gateway.gateway_url
  mcp_target_prefix = "mac-akto-ai-mcp"

  tags = merge(local.common_tags, {
    Phase = "2"
  })
}
