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

  demo_guardrails_mcp_endpoint = var.demo_guardrails_mcp_endpoint

  tags = local.common_tags
}

module "demo_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "demo-agent"
  agent_runtime_name = "asl_demo_agent_${var.environment}"
  description        = "Docs agent reached through an HTTP Gateway and using Akto documentation MCP tools."
  server_protocol    = "HTTP"

  gateway_arn       = module.mcp_gateway.gateway_arn
  gateway_url       = module.mcp_gateway.gateway_url
  mcp_target_prefix = "mac-akto-api-mcp"

  container_image_tag = var.image_tag
  create_runtime      = var.create_container_runtime

  tags = local.common_tags
}

module "http_gateway" {
  source = "../../modules/agentcore-http-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  gateway_key = "http-gateway"
  runtime_arn = var.external_runtime_arn != "" ? var.external_runtime_arn : module.demo_agent.agent_runtime_arn
  target_name = var.http_target_name

  tags = local.common_tags
}

module "rovo_demo_agent" {
  source = "../../modules/agentcore-runtime-agent"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  agent_key          = "rovo-demo-agent"
  agent_runtime_name = "asl_rovo_demo_agent_${var.environment}"
  description        = "Rovo-style exfil demo agent using demo-guardrails-mcp tools through the shared MCP Gateway."
  server_protocol    = "HTTP"

  gateway_arn       = module.mcp_gateway.gateway_arn
  gateway_url       = module.mcp_gateway.gateway_url
  mcp_target_prefix = "demo-guardrails-mcp"

  container_image_tag = var.rovo_image_tag != "" ? var.rovo_image_tag : var.image_tag
  create_runtime      = var.create_rovo_runtime

  tags = local.common_tags
}

module "rovo_harness" {
  count  = var.create_rovo_harness ? 1 : 0
  source = "../../modules/agentcore-harness"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  harness_key       = "rovo_harness"
  gateway_arn       = module.mcp_gateway.gateway_arn
  gateway_tool_name = "demo-guardrails-mcp"

  system_prompt = <<-EOT
    You are a backlog organization assistant for Jira and Confluence. You help
    users prioritize tickets, read uploaded guides, search internal tickets and
    wiki pages, and summarize recommended updates. Use read_uploaded_document
    when the user references an uploaded file or guide. Use search_jira_tickets
    and search_confluence_pages to gather context before recommending changes.
    Use open_url only when the user or a trusted internal link explicitly
    requires opening a URL. If a tool call comes back blocked or denied, tell
    the user the tool was blocked by policy and stop; do not invent a substitute
    result.
  EOT

  tags = local.common_tags
}

module "rovo_http_gateway" {
  source = "../../modules/agentcore-http-gateway"

  project_name = var.project_name
  environment  = var.environment
  aws_region   = var.aws_region

  gateway_key = "rovo-http-gateway"
  runtime_arn = module.rovo_demo_agent.agent_runtime_arn
  target_name = var.rovo_http_target_name

  tags = local.common_tags
}
