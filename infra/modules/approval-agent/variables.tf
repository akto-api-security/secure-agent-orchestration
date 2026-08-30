variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the Approval Agent runtime is deployed in."
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
  description = "Description of the Approval Agent runtime."
  type        = string
}

variable "container_image_tag" {
  description = <<-EOT
    Tag of the container image to deploy, already pushed to the Approval
    Agent's ECR repository. The image must exist in ECR *before* the
    aws_bedrockagentcore_agent_runtime resource can be created successfully
    -- apply this module once to create the ECR repository, build/push the
    image, then apply again to create the runtime.
  EOT
  type        = string
  default     = "latest"
}

variable "model_id" {
  description = "Bedrock model id used for the semantic (non-deterministic) approval rules only -- e.g. DAST-relevance classification. Never used for the deterministic sendFeedback rule."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "approval_pending_ttl_seconds" {
  description = "How long a PENDING approval/HITL request stays open for a human to decide, before it's considered expired."
  type        = number
  default     = 900
}

variable "grant_ttl_seconds" {
  description = "How long a signed grant remains valid for redemption after a human approves -- short-lived per the brief's explicit requirement."
  type        = number
  default     = 300
}

variable "log_level" {
  description = "Approval Agent LOG_LEVEL."
  type        = string
  default     = "INFO"
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
