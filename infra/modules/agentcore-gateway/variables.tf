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
