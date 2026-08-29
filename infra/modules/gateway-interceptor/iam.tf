data "aws_iam_policy_document" "interceptor_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "interceptor" {
  name               = "asl-interceptor-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.interceptor_assume_role.json
  tags               = var.tags
}

data "aws_caller_identity" "current" {}

# No DynamoDB/KMS/other state permissions -- Phase 4 scope is explicitly
# stateless (see docs/phase-checklist.md "Do NOT implement yet"). Logs only.
data "aws_iam_policy_document" "interceptor_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/asl-interceptor-${var.environment}:*",
    ]
  }
}

resource "aws_iam_role_policy" "interceptor_logs" {
  name   = "asl-interceptor-logs-${var.environment}"
  role   = aws_iam_role.interceptor.id
  policy = data.aws_iam_policy_document.interceptor_logs.json
}
