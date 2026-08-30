# All phases' resources live here via infra/modules/ -- Phase 1 (gateway),
# Phase 2 (delegated agents), Phase 3 (orchestrator), Phase 4
# (interceptor/OPA), Phase 5 (Approval Agent).

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Phase 5: Approval Agent -- owns all approval/HITL business logic
# (deterministic sendFeedback rule, semantic DAST classification, grant
# issuance/verification, human decision state). Defined before the
# interceptor module below since the interceptor needs its runtime ARN to
# call it; the Approval Agent has no dependency back on the interceptor or
# gateway, so this ordering avoids a circular module reference.
module "approval_agent" {
  source = "../../modules/approval-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_runtime_name = "asl_approval_agent_${var.environment}"
  description        = "Approval Agent -- owns deterministic approval and semantic HITL decisions, human decision state, and signed authorization grants for the Phase 4 interceptor."

  tags = merge(local.common_tags, {
    Phase = "5"
  })
}

# Phase 4: REQUEST interceptor Lambda, defined before the gateway module
# below since the gateway needs its ARN (to add an interceptor_configuration
# block + an IAM permission on its own service role) -- the interceptor
# itself has no dependency back on the gateway, so this ordering avoids a
# circular module reference.
module "gateway_interceptor" {
  source = "../../modules/gateway-interceptor"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region
  log_level    = var.interceptor_log_level

  # Phase 5: routes every OPA-allowed tools/call to the Approval Agent for
  # the authorization decision (see interceptor/handler.py).
  approval_agent_runtime_arn = module.approval_agent.agent_runtime_arn

  tags = merge(local.common_tags, {
    Phase = "4"
  })
}

module "agentcore_gateway" {
  source = "../../modules/agentcore-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  enable_interceptor     = true
  interceptor_lambda_arn = module.gateway_interceptor.lambda_arn

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

# Phase 3: Orchestrator -- the user-facing entry point. Classifies each
# question with a deterministic keyword match (router.py) and delegates to
# one of the two Phase 2 agents above over A2A (bedrock-agentcore
# invoke_agent_runtime). Never talks to the Gateway directly.
module "orchestrator" {
  source = "../../modules/agentcore-orchestrator"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_runtime_name = "asl_orchestrator_${var.environment}"
  description        = "Orchestrator Agent -- entry point for user questions; routes to the API Security Agent or Agentic Security Agent over A2A based on a deterministic keyword match."

  api_security_agent_runtime_arn     = module.api_security_agent.agent_runtime_arn
  agentic_security_agent_runtime_arn = module.agentic_security_agent.agent_runtime_arn
  # Phase 5: resumes a paused delegated-agent task by checking what a human
  # decided (read-only get_decision calls -- see approval_client.py).
  approval_agent_runtime_arn = module.approval_agent.agent_runtime_arn

  tags = merge(local.common_tags, {
    Phase = "3"
  })
}
