output "agent_runtime_arn" {
  description = "ARN of the AgentCore Runtime for this agent."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
}

output "agent_runtime_id" {
  description = "Unique identifier of the AgentCore Runtime for this agent."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}

output "execution_role_arn" {
  description = "ARN of the agent's AgentCore Runtime execution role."
  value       = aws_iam_role.execution.arn
}

output "ecr_repository_url" {
  description = "URL of the ECR repository this agent's container image must be pushed to."
  value       = aws_ecr_repository.this.repository_url
}

output "invoke_policy_arn" {
  description = <<-EOT
    ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime and
    bedrock-agentcore:GetAgentCard on this agent. Attach it to whichever IAM
    identity you'll use to test the agent's A2A interface (not attached
    automatically).
  EOT
  value       = aws_iam_policy.invoke_agent.arn
}
