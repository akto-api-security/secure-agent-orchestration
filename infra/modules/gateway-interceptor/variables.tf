variable "project_name" {
  description = "Project name, used for tagging."
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod, ...)."
  type        = string
}

variable "aws_region" {
  description = "AWS region this Lambda is deployed in."
  type        = string
}

variable "tags" {
  description = "Common tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}

variable "log_level" {
  description = <<-EOT
    Lambda LOG_LEVEL. Set to "DEBUG" for the first live test against the
    real Gateway, to log the raw interceptor event (see handler.py) and
    empirically confirm this account's actual event shape matches the
    schema handler.py assumes -- AWS's documentation, not a live invocation
    in this account, is what the schema was verified against so far. Drop
    back to "INFO" afterward; DEBUG isn't meant to run permanently.
  EOT
  type        = string
  default     = "INFO"
}
