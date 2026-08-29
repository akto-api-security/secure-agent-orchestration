variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region the gateway is deployed in."
  type        = string
}

variable "mcp_targets" {
  description = <<-EOT
    Remote MCP server targets to attach to the gateway, keyed by target
    name. Both are existing public Akto documentation MCP servers that
    require no outbound authentication (confirmed by direct probe).
  EOT
  type = map(object({
    endpoint = string
  }))
  default = {
    "mac-akto-api-mcp" = {
      endpoint = "https://docs.akto.io/~gitbook/mcp"
    }
    "mac-akto-ai-mcp" = {
      endpoint = "https://ai-security-docs.akto.io/~gitbook/mcp"
    }
  }
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "enable_interceptor" {
  description = <<-EOT
    Phase 4: whether to attach a REQUEST interceptor to the gateway. A plain
    boolean, not inferred from interceptor_lambda_arn being non-null -- the
    ARN comes from another module and is unknown at plan time on a first
    apply, and Terraform can't evaluate a `count`/`for_each` based on an
    unknown value. Keeping this as its own literal keeps the conditional
    resources' counts resolvable at plan time regardless of whether the
    interceptor Lambda has been created yet.
  EOT
  type        = bool
  default     = false
}

variable "interceptor_lambda_arn" {
  description = <<-EOT
    Phase 4: ARN of the REQUEST interceptor Lambda (from the
    gateway-interceptor module). Only used when enable_interceptor = true.
  EOT
  type        = string
  default     = null
}
