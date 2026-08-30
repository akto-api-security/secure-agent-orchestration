output "agent_runtime_arn" {
  description = "ARN of the Approval Agent's AgentCore Runtime."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn
}

output "agent_runtime_id" {
  description = "Unique identifier of the Approval Agent's AgentCore Runtime."
  value       = aws_bedrockagentcore_agent_runtime.this.agent_runtime_id
}

output "execution_role_arn" {
  description = "ARN of the Approval Agent's AgentCore Runtime execution role."
  value       = aws_iam_role.execution.arn
}

output "ecr_repository_url" {
  description = "URL of the ECR repository the Approval Agent's container image must be pushed to."
  value       = aws_ecr_repository.this.repository_url
}

output "invoke_policy_arn" {
  description = <<-EOT
    ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime on
    the Approval Agent. Attach it to whichever IAM identity you'll use to
    test it directly (not attached automatically).
  EOT
  value       = aws_iam_policy.invoke_approval_agent.arn
}

output "state_table_name" {
  description = "Name of the DynamoDB table holding approval/HITL workflow state."
  value       = aws_dynamodb_table.approval_state.name
}

output "state_table_arn" {
  description = "ARN of the DynamoDB table holding approval/HITL workflow state."
  value       = aws_dynamodb_table.approval_state.arn
}

output "grant_kms_key_arn" {
  description = "ARN of the KMS key used to sign/verify authorization grants."
  value       = aws_kms_key.grants.arn
}
