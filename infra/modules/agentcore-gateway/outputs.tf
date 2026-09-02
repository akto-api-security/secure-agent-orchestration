output "gateway_id" {
  description = "Unique identifier of the AgentCore Gateway."
  value       = aws_bedrockagentcore_gateway.this.gateway_id
}

output "gateway_arn" {
  description = "ARN of the AgentCore Gateway."
  value       = aws_bedrockagentcore_gateway.this.gateway_arn
}

output "gateway_url" {
  description = "MCP endpoint URL for the gateway (tools/list, tools/call)."
  value       = aws_bedrockagentcore_gateway.this.gateway_url
}

output "gateway_role_arn" {
  description = "ARN of the gateway's IAM service role."
  value       = aws_iam_role.gateway.arn
}

output "target_ids" {
  description = "Gateway target IDs, keyed by target name."
  value = {
    "mac-akto-api-mcp" = aws_bedrockagentcore_gateway_target.api_docs.target_id
    "mac-akto-ai-mcp"  = aws_bedrockagentcore_gateway_target.ai_docs.target_id
  }
}
