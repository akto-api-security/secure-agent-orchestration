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

# Phase 5: the interceptor's only new permission -- it calls the Approval
# Agent for every OPA-allowed tools/call, but still holds no DynamoDB/KMS
# access itself (that stays entirely inside the Approval Agent's own
# execution role -- see docs/phase-context/phase-5-context.md, "IAM"). Both
# ARN forms are granted, matching the pattern already confirmed necessary
# for bedrock-agentcore:InvokeAgentRuntime elsewhere in this project (Phase
# 3's orchestrator module).
data "aws_iam_policy_document" "invoke_approval_agent" {
  statement {
    effect = "Allow"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
    ]
    resources = [
      var.approval_agent_runtime_arn,
      "${var.approval_agent_runtime_arn}/runtime-endpoint/*",
    ]
  }
}

resource "aws_iam_role_policy" "interceptor_invoke_approval_agent" {
  name   = "asl-interceptor-invoke-approval-agent-${var.environment}"
  role   = aws_iam_role.interceptor.id
  policy = data.aws_iam_policy_document.invoke_approval_agent.json
}
