output "http_gateway_id" {
  value = module.http_gateway.gateway_id
}

output "http_gateway_arn" {
  value = module.http_gateway.gateway_arn
}

output "http_gateway_url" {
  value = module.http_gateway.gateway_url
}

output "http_gateway_target_name" {
  value = module.http_gateway.target_name
}

output "http_gateway_invoke_policy_arn" {
  description = "Attach this policy to the IAM identity that calls the agent."
  value       = module.http_gateway.invoke_policy_arn
}

output "mcp_gateway_id" {
  value = module.mcp_gateway.gateway_id
}

output "mcp_gateway_arn" {
  value = module.mcp_gateway.gateway_arn
}

output "mcp_gateway_url" {
  value = module.mcp_gateway.gateway_url
}

output "demo_agent_ecr_repository_url" {
  value = module.demo_agent.ecr_repository_url
}

output "demo_agent_runtime_arn" {
  value = module.demo_agent.agent_runtime_arn
}

output "demo_agent_runtime_id" {
  value = module.demo_agent.agent_runtime_id
}
