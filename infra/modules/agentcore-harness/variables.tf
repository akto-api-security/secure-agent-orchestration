variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name used in resource names."
  type        = string
}

variable "aws_region" {
  description = "AWS region for the harness."
  type        = string
}

variable "harness_key" {
  description = "Short identifier for the harness (asl_<harness_key>_<environment>)."
  type        = string
}

variable "gateway_arn" {
  description = "AgentCore MCP Gateway ARN attached as agentcore_gateway tool."
  type        = string
}

variable "gateway_tool_name" {
  description = "Tool name exposed to the harness for the MCP gateway."
  type        = string
  default     = "demo-guardrails-mcp"
}

variable "model_id" {
  description = "Bedrock model ID for the harness loop."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "system_prompt" {
  description = "System prompt for the harness agent."
  type        = string
}

variable "max_iterations" {
  description = "Maximum agent loop iterations."
  type        = number
  default     = 20
}

variable "timeout_seconds" {
  description = "Harness invocation timeout in seconds."
  type        = number
  default     = 900
}

variable "tags" {
  description = "Common tags applied to resources."
  type        = map(string)
  default     = {}
}
