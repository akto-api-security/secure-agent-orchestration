output "agent_runtime_arn" {
  description = "ARN of the Orchestrator's AgentCore Runtime."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
}

output "agent_runtime_id" {
  description = "Unique identifier of the Orchestrator's AgentCore Runtime."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}

output "execution_role_arn" {
  description = "ARN of the Orchestrator's AgentCore Runtime execution role."
  value       = aws_iam_role.execution.arn
}

output "ecr_repository_url" {
  description = "URL of the ECR repository the orchestrator's container image must be pushed to."
  value       = aws_ecr_repository.this.repository_url
}

output "invoke_policy_arn" {
  description = <<-EOT
    ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime on
    the orchestrator. Attach it to whichever IAM identity you'll use to test
    it directly (not attached automatically).
  EOT
  value       = aws_iam_policy.invoke_orchestrator.arn
}
