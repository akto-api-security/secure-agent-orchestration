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
