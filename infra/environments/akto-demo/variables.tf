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
