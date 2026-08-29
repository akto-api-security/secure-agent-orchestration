output "lambda_arn" {
  description = "ARN of the interceptor Lambda -- fed into the agentcore-gateway module's interceptor_lambda_arn variable."
  value       = aws_lambda_function.interceptor.arn
}

output "lambda_function_name" {
  description = "Name of the interceptor Lambda function."
  value       = aws_lambda_function.interceptor.function_name
}

output "execution_role_arn" {
  description = "ARN of the interceptor Lambda's execution role."
  value       = aws_iam_role.interceptor.arn
}

output "log_group_name" {
  description = "CloudWatch log group for the interceptor Lambda."
  value       = aws_cloudwatch_log_group.interceptor.name
}
