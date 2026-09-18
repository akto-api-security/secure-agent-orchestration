data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "assume_role" {
  statement {
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
      values = [
        "arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:gateway/asl-${var.gateway_key}-${var.environment}-*",
      ]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "asl-${var.gateway_key}-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "gateway" {
  statement {
    sid       = "InvokeRuntime"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:InvokeAgentRuntime"]
    resources = [var.runtime_arn, "${var.runtime_arn}/*"]
  }

  statement {
    sid    = "WriteGatewayLogs"
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

resource "aws_iam_role_policy" "gateway" {
  name   = "asl-${var.gateway_key}-${var.environment}"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway.json
}

data "aws_iam_policy_document" "invoke_gateway" {
  statement {
    sid       = "InvokeHttpGateway"
    effect    = "Allow"
    actions   = ["bedrock-agentcore:InvokeGateway"]
    resources = [aws_bedrockagentcore_gateway.this.gateway_arn]
  }
}

resource "aws_iam_policy" "invoke_gateway" {
  name        = "asl-${var.gateway_key}-invoke-${var.environment}"
  description = "Allows a caller to invoke the HTTP Gateway (asl-${var.gateway_key}-${var.environment})."
  policy      = data.aws_iam_policy_document.invoke_gateway.json
  tags        = var.tags
}
