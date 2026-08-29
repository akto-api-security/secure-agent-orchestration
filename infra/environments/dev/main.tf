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
