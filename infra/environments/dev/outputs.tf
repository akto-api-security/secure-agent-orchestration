output "gateway_id" {
  description = "Unique identifier of the AgentCore Gateway."
  value       = module.agentcore_gateway.gateway_id
}

output "gateway_arn" {
  description = "ARN of the AgentCore Gateway."
  value       = module.agentcore_gateway.gateway_arn
}

output "gateway_url" {
  description = "MCP endpoint URL for the gateway (tools/list, tools/call)."
  value       = module.agentcore_gateway.gateway_url
}

output "gateway_role_arn" {
  description = "ARN of the gateway's IAM service role."
  value       = module.agentcore_gateway.gateway_role_arn
}

output "invoke_policy_arn" {
  description = "ARN of the IAM policy granting bedrock-agentcore:InvokeGateway on this gateway. Attach it to whichever IAM identity you'll use to test tools/list and tools/call."
  value       = module.agentcore_gateway.invoke_policy_arn
}

output "target_ids" {
  description = "Gateway target IDs, keyed by target name."
  value       = module.agentcore_gateway.target_ids
}

output "api_security_agent_ecr_repository_url" {
  description = "ECR repository URL to push the API Security Agent's container image to, before first apply of its agent runtime."
  value       = module.api_security_agent.ecr_repository_url
}

output "api_security_agent_runtime_arn" {
  description = "ARN of the API Security Agent's AgentCore Runtime."
  value       = module.api_security_agent.agent_runtime_arn
}

output "api_security_agent_execution_role_arn" {
  description = "ARN of the API Security Agent's AgentCore Runtime execution role."
  value       = module.api_security_agent.execution_role_arn
}

output "api_security_agent_invoke_policy_arn" {
  description = "ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime/GetAgentCard on the API Security Agent. Attach it to whichever identity you'll test with."
  value       = module.api_security_agent.invoke_policy_arn
}

output "agentic_security_agent_ecr_repository_url" {
  description = "ECR repository URL to push the Agentic Security Agent's container image to, before first apply of its agent runtime."
  value       = module.agentic_security_agent.ecr_repository_url
}

output "agentic_security_agent_runtime_arn" {
  description = "ARN of the Agentic Security Agent's AgentCore Runtime."
  value       = module.agentic_security_agent.agent_runtime_arn
}

output "agentic_security_agent_execution_role_arn" {
  description = "ARN of the Agentic Security Agent's AgentCore Runtime execution role."
  value       = module.agentic_security_agent.execution_role_arn
}

output "agentic_security_agent_invoke_policy_arn" {
  description = "ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime/GetAgentCard on the Agentic Security Agent. Attach it to whichever identity you'll test with."
  value       = module.agentic_security_agent.invoke_policy_arn
}

output "orchestrator_ecr_repository_url" {
  description = "ECR repository URL to push the Orchestrator's container image to, before first apply of its agent runtime."
  value       = module.orchestrator.ecr_repository_url
}

output "orchestrator_runtime_arn" {
  description = "ARN of the Orchestrator's AgentCore Runtime."
  value       = module.orchestrator.agent_runtime_arn
}

output "orchestrator_execution_role_arn" {
  description = "ARN of the Orchestrator's AgentCore Runtime execution role."
  value       = module.orchestrator.execution_role_arn
}

output "orchestrator_invoke_policy_arn" {
  description = "ARN of the IAM policy granting bedrock-agentcore:InvokeAgentRuntime on the Orchestrator. Attach it to whichever identity you'll test with."
  value       = module.orchestrator.invoke_policy_arn
}
