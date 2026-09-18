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
  description = "Attach this policy to the IAM identity that calls the docs agent."
  value       = module.http_gateway.invoke_policy_arn
}

output "rovo_http_gateway_id" {
  value = module.rovo_http_gateway.gateway_id
}

output "rovo_http_gateway_arn" {
  value = module.rovo_http_gateway.gateway_arn
}

output "rovo_http_gateway_url" {
  value = module.rovo_http_gateway.gateway_url
}

output "rovo_http_gateway_target_name" {
  value = module.rovo_http_gateway.target_name
}

output "rovo_http_gateway_invoke_policy_arn" {
  description = "Attach this policy to the IAM identity that calls the Rovo demo agent."
  value       = module.rovo_http_gateway.invoke_policy_arn
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

output "rovo_demo_agent_ecr_repository_url" {
  value = module.rovo_demo_agent.ecr_repository_url
}

output "rovo_demo_agent_runtime_arn" {
  value = module.rovo_demo_agent.agent_runtime_arn
}

output "rovo_demo_agent_runtime_id" {
  value = module.rovo_demo_agent.agent_runtime_id
}

output "rovo_harness_arn" {
  value = try(module.rovo_harness[0].harness_arn, "")
}

output "rovo_harness_id" {
  value = try(module.rovo_harness[0].harness_id, "")
}

output "rovo_harness_name" {
  value = try(module.rovo_harness[0].harness_name, "")
}
