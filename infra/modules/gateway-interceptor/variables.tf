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

variable "approval_agent_runtime_arn" {
  description = <<-EOT
    Phase 5: ARN of the Approval Agent's AgentCore Runtime (from the
    approval-agent module). The interceptor calls this synchronously for
    every OPA-allowed tools/call to get the authorization decision --
    required, no sensible fallback if unset (see handler.py, which reads
    this via a required environment variable).
  EOT
  type        = string
}

variable "lambda_timeout_seconds" {
  description = <<-EOT
    Phase 5: bumped from Phase 4's 10s default to comfortably cover an
    Approval Agent round trip, which may itself include a Bedrock model
    call for a semantic decision. No AWS-documented hard timeout was found
    for how long the Gateway waits on the interceptor (see
    docs/phase-context/phase-5-context.md) -- this is a defensive choice,
    not a value derived from a confirmed AWS limit.
  EOT
  type        = number
  default     = 30
}
