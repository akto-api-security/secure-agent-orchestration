output "gateway_id" {
  value = aws_bedrockagentcore_gateway.this.gateway_id
}

output "gateway_arn" {
  value = aws_bedrockagentcore_gateway.this.gateway_arn
}

output "gateway_url" {
  value = aws_bedrockagentcore_gateway.this.gateway_url
}

output "gateway_role_arn" {
  value = aws_iam_role.gateway.arn
}

output "target_name" {
  value = aws_bedrockagentcore_gateway_target.runtime.name
}

output "invoke_policy_arn" {
  value = aws_iam_policy.invoke_gateway.arn
}
