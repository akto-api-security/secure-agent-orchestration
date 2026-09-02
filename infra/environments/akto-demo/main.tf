locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

module "mcp_gateway" {
  source = "../../modules/agentcore-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  tags = local.common_tags
}

module "demo_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "demo-agent"
  agent_runtime_name = "asl_demo_agent_${var.environment}"
  description        = "Demo agent reached through an HTTP Gateway and using MCP tools through a second Gateway."
  server_protocol    = "HTTP"

  gateway_arn       = module.mcp_gateway.gateway_arn
  gateway_url       = module.mcp_gateway.gateway_url
  mcp_target_prefix = "mac-akto-api-mcp"

  container_image_tag = var.image_tag

  tags = local.common_tags
}

module "http_gateway" {
  source = "../../modules/agentcore-http-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  runtime_arn = module.demo_agent.agent_runtime_arn
  target_name = var.http_target_name

  tags = local.common_tags
}
