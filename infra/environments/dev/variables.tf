variable "aws_region" {
  description = "AWS region for this environment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name, used as a resource-naming prefix."
  type        = string
  default     = "agent-security-lab"
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
  default     = "dev"
}

variable "image_tag" {
  description = <<-EOT
    Immutable tag applied to all 4 service images (orchestrator,
    API Security Agent, Agentic Security Agent, Approval Agent) --
    scripts/build-and-push.sh tags/pushes every image with this same
    value (defaults to a git short SHA there, never "latest"). Defaults to
    "latest" here only so this variable's addition doesn't change the
    already-deployed dev stack's behavior until deliberately overridden --
    a customer deployment should always pass an explicit version, e.g.
    `terraform apply -var="image_tag=abc1234"`.
  EOT
  type        = string
  default     = "latest"
}

variable "interceptor_log_level" {
  description = <<-EOT
    Interceptor Lambda LOG_LEVEL. Set to "DEBUG" for the first
    live test against the real Gateway to log the raw interceptor event
    (see interceptor/handler.py) -- e.g.
    `terraform apply -var 'interceptor_log_level=DEBUG'`. Drop back to the
    "INFO" default afterward.
  EOT
  type        = string
  default     = "INFO"
}
