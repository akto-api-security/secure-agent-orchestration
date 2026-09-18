output "harness_arn" {
  value = aws_bedrockagentcore_harness.this.arn
}

output "harness_id" {
  value = aws_bedrockagentcore_harness.this.harness_id
}

output "harness_name" {
  value = aws_bedrockagentcore_harness.this.harness_name
}

output "execution_role_arn" {
  value = aws_iam_role.harness.arn
}
