variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the orchestrator runtime is deployed in."
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
  description = "Description of the orchestrator agent runtime."
  type        = string
}

variable "api_security_agent_runtime_arn" {
  description = "ARN of the Phase 2 API Security Agent's AgentCore Runtime. The orchestrator is granted InvokeAgentRuntime/GetAgentCard scoped to this ARN only."
  type        = string
}

variable "agentic_security_agent_runtime_arn" {
  description = "ARN of the Phase 2 Agentic Security Agent's AgentCore Runtime. The orchestrator is granted InvokeAgentRuntime/GetAgentCard scoped to this ARN only."
  type        = string
}

variable "container_image_tag" {
  description = <<-EOT
    Tag of the container image to deploy, already pushed to the orchestrator's
    ECR repository. The image must exist in ECR *before* the
    aws_bedrockagentcore_agent_runtime resource can be created successfully
    -- apply this module once to create the ECR repository, build/push the
    image, then apply again to create the runtime.
  EOT
  type        = string
  default     = "latest"
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
