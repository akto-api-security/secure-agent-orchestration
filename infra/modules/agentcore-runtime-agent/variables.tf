variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the agent runtime is deployed in."
  type        = string
}

variable "agent_key" {
  description = <<-EOT
    Short, hyphenated identifier for this agent (e.g. "api-security-agent").
    Used to derive the ECR repository name and IAM role/policy names, which
    allow hyphens (unlike agent_runtime_name, see below).
  EOT
  type        = string
}

variable "agent_runtime_name" {
  description = <<-EOT
    Name passed to aws_bedrockagentcore_agent_runtime.agent_runtime_name.
    Must match AgentCore's naming constraint on CreateAgentRuntime
    (`[a-zA-Z][a-zA-Z0-9_]{0,47}`) -- letters, digits, and underscores only,
    no hyphens, max 48 characters.
  EOT
  type        = string
}

variable "description" {
  description = "Description of the agent runtime."
  type        = string
}

variable "gateway_arn" {
  description = "ARN of the Phase 1 AgentCore Gateway this agent is allowed to invoke."
  type        = string
}

variable "gateway_url" {
  description = "MCP endpoint URL of the Phase 1 AgentCore Gateway, passed to the container as GATEWAY_URL."
  type        = string
}

variable "mcp_target_prefix" {
  description = <<-EOT
    Gateway target name this agent should scope its MCP tool discovery to
    (tools/list results are namespaced "<target_prefix>___<tool_name>"),
    e.g. "mac-akto-api-mcp".
  EOT
  type        = string
}

variable "container_image_tag" {
  description = <<-EOT
    Tag of the container image to deploy, already pushed to this agent's ECR
    repository. The image must exist in ECR *before* the
    aws_bedrockagentcore_agent_runtime resource can be created successfully
    -- apply this module once to create the ECR repository, build/push the
    image, then apply again to create the runtime.
  EOT
  type        = string
  default     = "latest"
}

variable "model_id" {
  description = "Bedrock model id (or cross-region inference profile id) the agent uses for reasoning."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
