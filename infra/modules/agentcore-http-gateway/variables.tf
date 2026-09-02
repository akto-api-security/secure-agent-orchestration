variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name used in resource names."
  type        = string
}

variable "aws_region" {
  description = "AWS region containing the gateway and runtime."
  type        = string
}

variable "runtime_arn" {
  description = "AgentCore Runtime ARN routed through this HTTP Gateway."
  type        = string
}

variable "target_name" {
  description = "HTTP Gateway target name used in the invocation URL."
  type        = string
  default     = "demo-agent"
}

variable "tags" {
  description = "Common tags applied to resources."
  type        = map(string)
  default     = {}
}
