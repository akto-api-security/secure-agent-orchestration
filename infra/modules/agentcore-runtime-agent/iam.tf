data "aws_caller_identity" "current" {}

# Trust policy per AWS's documented AgentCore Runtime execution-role trust
# policy: bedrock-agentcore.amazonaws.com may assume this role only for a
# bedrock-agentcore resource in this account/region. Unlike the Gateway's
# service role (Phase 1), there's no circular dependency here -- the
# runtime's name (and therefore aws:SourceArn) is chosen by us up front, so
# the SourceArn condition can be scoped at creation time rather than added
# as a follow-up.
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
  name               = "asl-${var.agent_key}-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

# Baseline execution permissions follow AWS's documented "AgentCore Runtime
# execution role" reference policy verbatim (ECR pull, logs, X-Ray,
# CloudWatch metrics, workload-identity tokens, Bedrock model invocation --
# https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-permissions.html),
# plus one project-specific addition: bedrock-agentcore:InvokeGateway scoped
# to the Phase 1 gateway only (not all gateways in the account), mirroring
# the least-privilege pattern already used for asl-gateway-invoke-dev in
# Phase 1.
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
    sid    = "BedrockModelInvocation"
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
    sid       = "InvokePhase1Gateway"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [var.gateway_arn]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "asl-${var.agent_key}-execution-${var.environment}"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# Standalone policy (not auto-attached to anything), mirroring
# asl-gateway-invoke-dev from Phase 1: grants the two actions needed to
# directly test this agent's A2A interface over SigV4 -- InvokeAgentRuntime
# to send a task, GetAgentCard to fetch its agent card (a separately
# grantable action; InvokeAgentRuntime alone does not cover it). Attach it
# manually to whichever IAM identity you test with.
data "aws_iam_policy_document" "invoke_agent" {
  statement {
    sid    = "AllowAgentRuntimeInvocation"
    effect = "Allow"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
      "bedrock-agentcore:GetAgentCard",
    ]
    resources = [aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn]
  }
}

resource "aws_iam_policy" "invoke_agent" {
  name        = "asl-${var.agent_key}-invoke-${var.environment}"
  description = "Allows invoking the asl-${var.agent_key}-${var.environment} AgentCore Runtime agent over A2A (message/send, agent-card fetch)."
  policy      = data.aws_iam_policy_document.invoke_agent.json
  tags        = var.tags
}
