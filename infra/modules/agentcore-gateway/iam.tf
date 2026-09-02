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
