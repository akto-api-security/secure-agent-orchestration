data "aws_caller_identity" "current" {}

# Same trust policy shape as infra/modules/agentcore-runtime-agent (Phase 2):
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
  name               = "asl-orchestrator-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

# Baseline execution permissions follow the same AWS-documented "AgentCore
# Runtime execution role" reference policy as Phase 2's agents (ECR pull,
# logs, X-Ray, CloudWatch metrics, workload-identity tokens) -- but
# deliberately omits bedrock:InvokeModel (the orchestrator routes with a
# deterministic keyword match, no model call) and omits
# bedrock-agentcore:InvokeGateway entirely (the orchestrator never talks to
# the Gateway directly, per the Phase 3 IAM boundary). The one
# project-specific addition is InvokeAgentRuntime scoped to exactly the two
# Phase 2 delegated agents, not "*" (GetAgentCard is not granted -- see the
# InvokeDelegatedAgents statement below for why).
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

  # GetAgentCard is intentionally not granted here: a2a_client.py only ever
  # calls invoke_agent_runtime (a message/send JSON-RPC body), never fetches
  # either delegated agent's card, so there's nothing to grant it for.
  #
  # Resources list BOTH the bare runtime ARN and the /runtime-endpoint/*
  # sub-resource. Confirmed empirically across two otherwise-identical calls
  # (same code path, same agentRuntimeArn, no qualifier passed) that AWS's
  # bedrock-agentcore:InvokeAgentRuntime authorization check is inconsistent
  # about which ARN form it evaluates against: one live AccessDenied error
  # named arn:...:runtime/<id>/runtime-endpoint/DEFAULT, a second (after
  # granting only that form) named the bare arn:...:runtime/<id> instead.
  # Granting both is the only way to cover it reliably given that
  # inconsistency, which looks like a rough edge in this still-new AgentCore
  # Runtime data-plane API rather than something on our side. Phase 2's own
  # asl-<agent>-invoke-<env> policies (bare ARN only) likely have this same
  # gap; it hasn't surfaced there because the human identities testing them
  # probably have broader permissions elsewhere.
  statement {
    sid     = "InvokeDelegatedAgents"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      var.api_security_agent_runtime_arn,
      "${var.api_security_agent_runtime_arn}/runtime-endpoint/*",
      var.agentic_security_agent_runtime_arn,
      "${var.agentic_security_agent_runtime_arn}/runtime-endpoint/*",
    ]
  }

  # Phase 5: read-only from the orchestrator's perspective -- its own code
  # (approval_client.py) only ever sends action=get_decision, never
  # decide/authorize. Terraform/IAM can't distinguish payload-level actions
  # on the same InvokeAgentRuntime call, so this is enforced by this
  # project's own code, not by IAM alone (see docs/phase-context/phase-5-context.md,
  # "IAM").
  statement {
    sid     = "InvokeApprovalAgent"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      var.approval_agent_runtime_arn,
      "${var.approval_agent_runtime_arn}/runtime-endpoint/*",
    ]
  }
}

resource "aws_iam_role_policy" "execution" {
  name   = "asl-orchestrator-execution-${var.environment}"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution.json
}

# Standalone policy (not auto-attached), mirroring the asl-<agent>-invoke-<env>
# policies from Phase 2: grants bedrock-agentcore:InvokeAgentRuntime scoped
# to the orchestrator's own runtime, for whichever identity you use to test
# it directly. GetAgentCard is omitted here (unlike Phase 2's agents) since
# the orchestrator's inbound protocol is HTTP, not A2A -- there's no agent
# card to fetch.
#
# Resource lists both the bare runtime ARN and the /runtime-endpoint/*
# sub-resource -- see the InvokeDelegatedAgents statement above for why:
# confirmed empirically that AWS's authorization check for this action is
# inconsistent about which ARN form it evaluates against.
data "aws_iam_policy_document" "invoke_orchestrator" {
  statement {
    sid     = "AllowOrchestratorInvocation"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [
      aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn,
      "${aws_bedrockagentcore_agent_runtime.this.agent_runtime_arn}/runtime-endpoint/*",
    ]
  }
}

resource "aws_iam_policy" "invoke_orchestrator" {
  name        = "asl-orchestrator-invoke-${var.environment}"
  description = "Allows invoking the asl-orchestrator-${var.environment} AgentCore Runtime over its HTTP protocol interface (/invocations)."
  policy      = data.aws_iam_policy_document.invoke_orchestrator.json
  tags        = var.tags
}
