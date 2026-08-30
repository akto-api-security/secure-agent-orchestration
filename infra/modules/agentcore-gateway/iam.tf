data "aws_caller_identity" "current" {}

# Trust policy for the gateway's own service role. Scoped to this account
# only (aws:SourceAccount) — a SourceArn condition scoped to this specific
# gateway's ARN can't be added yet because the gateway doesn't exist until
# after this role is created (circular dependency). Tighten with a SourceArn
# condition once the gateway ARN is known, per AWS's own guidance for this
# exact case.
data "aws_iam_policy_document" "gateway_assume_role" {
  statement {
    sid     = "GatewayAssumeRolePolicy"
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
  }
}

resource "aws_iam_role" "gateway" {
  name               = "asl-gateway-service-role-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.gateway_assume_role.json
  tags               = var.tags
}

# The two MCP targets require no outbound authentication (confirmed by
# direct probe), so the service role needs no Secrets Manager or SigV4
# permissions — only the ability to write its own gateway logs.
data "aws_iam_policy_document" "gateway_logs" {
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/gateways/*",
    ]
  }
}

resource "aws_iam_role_policy" "gateway_logs" {
  name   = "asl-gateway-logs-${var.environment}"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway_logs.json
}

# Inbound authorization is AWS_IAM: any caller that invokes the gateway must
# sign the request with SigV4 credentials that carry this permission. This
# policy is not auto-attached to any identity (the identity you'll test with
# isn't Terraform-managed) — attach it manually to whichever IAM user/role
# you invoke the gateway with.
data "aws_iam_policy_document" "invoke_gateway" {
  statement {
    sid       = "AllowGatewayInvocation"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [aws_bedrockagentcore_gateway.this.gateway_arn]
  }
}

resource "aws_iam_policy" "invoke_gateway" {
  name        = "asl-gateway-invoke-${var.environment}"
  description = "Allows invoking the asl-gateway-${var.environment} AgentCore Gateway (tools/list, tools/call)."
  policy      = data.aws_iam_policy_document.invoke_gateway.json
  tags        = var.tags
}

# The gateway's own service role must be able to invoke the interceptor
# Lambda (a confirmed AWS requirement for gateways that configure an
# interceptor). Identity-based only; no Lambda-side resource policy is added
# (not documented as required for this same-account, execution-role-mediated
# invocation, and adding one scoped to the gateway's own ARN would create a
# circular module dependency).
data "aws_iam_policy_document" "invoke_interceptor" {
  count = var.enable_interceptor ? 1 : 0

  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [var.interceptor_lambda_arn]
  }
}

resource "aws_iam_role_policy" "gateway_invoke_interceptor" {
  count  = var.enable_interceptor ? 1 : 0
  name   = "asl-gateway-invoke-interceptor-${var.environment}"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.invoke_interceptor[0].json
}
