variable "aws_region" {
  description = "AWS region for this environment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name, used as a resource-naming prefix."
  type        = string
  default     = "agentcore-gateway-demo"
}

variable "environment" {
  description = "Environment name used in resource names."
  type        = string
  default     = "demo"
}

variable "image_tag" {
  description = "Immutable tag of the demo agent image already pushed to ECR."
  type        = string
  default     = "latest"
}

variable "http_target_name" {
  description = "Target path exposed by the outer HTTP Gateway."
  type        = string
  default     = "demo-agent"
}

variable "create_container_runtime" {
  description = "When false, skip ECR Runtime; use scripts/deploy-zip.sh instead."
  type        = bool
  default     = true
}

variable "external_runtime_arn" {
  description = "Zip-deployed Runtime ARN for the HTTP Gateway (create_container_runtime=false)."
  type        = string
  default     = ""
}

variable "demo_guardrails_mcp_endpoint" {
  description = "Public HTTPS MCP URL for examples/demo-guardrails-mcp (set by scripts/register-demo-mcp-target.sh)."
  type        = string
  default     = ""
}

variable "rovo_http_target_name" {
  description = "Target path exposed by the Rovo demo HTTP Gateway."
  type        = string
  default     = "rovo-demo-agent"
}

variable "rovo_image_tag" {
  description = "ECR image tag for the Rovo demo agent. Empty uses image_tag."
  type        = string
  default     = ""
}

variable "create_rovo_runtime" {
  description = "When true, create the Rovo demo AgentCore Runtime from ECR."
  type        = bool
  default     = true
}

variable "create_rovo_harness" {
  description = "When true, create the Rovo demo AgentCore Harness."
  type        = bool
  default     = true
}
