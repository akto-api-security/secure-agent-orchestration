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

variable "interceptor_log_level" {
  description = <<-EOT
    Phase 4: interceptor Lambda LOG_LEVEL. Set to "DEBUG" for the first
    live test against the real Gateway to log the raw interceptor event
    (see interceptor/handler.py) -- e.g.
    `terraform apply -var 'interceptor_log_level=DEBUG'`. Drop back to the
    "INFO" default afterward.
  EOT
  type        = string
  default     = "INFO"
}
