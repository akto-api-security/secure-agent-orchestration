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
