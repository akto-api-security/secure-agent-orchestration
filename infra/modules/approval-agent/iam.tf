data "aws_caller_identity" "current" {}

# Same trust policy shape as the other AgentCore Runtime agents:
# bedrock-agentcore.amazonaws.com may assume this role only for a
# bedrock-agentcore resource in this account/region.
data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "AssumeRolePolicy"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "asl-approval-agent-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

# Baseline execution permissions follow the same AWS-documented "AgentCore
# Runtime execution role" reference policy as the other agents (ECR pull,
# logs, X-Ray, CloudWatch metrics, workload-identity tokens), plus the
# permissions this agent actually needs and nothing else: DynamoDB on its
# own state table, KMS Sign/Verify on its own grants key, and
# bedrock:InvokeModel scoped to the one model used for semantic (DAST)
# classification. Deliberately NO bedrock-agentcore:InvokeGateway -- the
# Approval Agent never talks to the Gateway/MCP targets directly; it only
# ever receives calls from the interceptor and the orchestrator/human CLI.
data "aws_iam_policy_document" "execution" {
  statement {
    sid       = "ECRImageAccess"
    effect    = "Allow"
    actions   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [aws_ecr_repository.this.arn]
  }

  statement {
    sid       = "ECRTokenAccess"
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid     = "LogGroupCreation"
    effect  = "Allow"
    actions = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*",
    ]
  }

  statement {
    sid     = "LogGroupPolicy"
    effect  = "Allow"
    actions = ["logs:PutResourcePolicy"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/${var.agent_runtime_name}-*",
    ]
  }

  statement {
    sid       = "LogGroupDescribe"
    effect    = "Allow"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  statement {
    sid     = "LogStreamWrite"
    effect  = "Allow"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
    ]
  }

  statement {
    sid    = "Tracing"
    effect = "Allow"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "Metrics"
    effect    = "Allow"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }

  statement {
    sid    = "GetAgentAccessToken"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:GetWorkloadAccessToken",
      "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
      "bedrock-agentcore:GetWorkloadAccessTokenForUserId",
    ]
    resources = [
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
      "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${var.agent_runtime_name}-*",
    ]
  }

  statement {
    sid    = "SemanticClassificationModel"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      "arn:aws:bedrock:*::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*",
    ]
  }

  statement {
    sid       = "ApprovalStateTable"
    effect    = "Allow"
    actions   = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"]
    resources = [aws_dynamodb_table.approval_state.arn]
  }

  statement {
    sid       = "SignAndVerifyGrants"
    effect    = "Allow"
    actions   = ["kms:Sign", "kms:Verify"]
    resources = [aws_kms_key.grants.arn]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "asl-approval-agent-execution-${var.environment}"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# Standalone policy (not auto-attached), mirroring the other agents'
# asl-<agent>-invoke-<env> pattern -- for manually testing this runtime's
# HTTP protocol interface directly. Resource lists both the bare runtime ARN
# and the /runtime-endpoint/* sub-resource (see the Orchestrator module's own
# comment on this -- confirmed empirically in that module that
# bedrock-agentcore:InvokeAgentRuntime is checked inconsistently against
# either ARN form).
data "aws_iam_policy_document" "invoke_approval_agent" {
  statement {
    sid    = "AllowApprovalAgentInvocation"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
    ]
    resources = [
      aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn,
      "${aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn}/runtime-endpoint/*",
    ]
  }
}

resource "aws_iam_policy" "invoke_approval_agent" {
  name        = "asl-approval-agent-invoke-${var.environment}"
  description = "Allows invoking the asl-approval-agent-${var.environment} AgentCore Runtime over its HTTP protocol interface (/invocations)."
  policy      = data.aws_iam_policy_document.invoke_approval_agent.json
  tags        = var.tags
}
