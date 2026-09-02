resource "aws_bedrockagentcore_gateway" "this" {
  name            = "asl-http-gateway-${var.environment}"
  role_arn        = aws_iam_role.gateway.arn
  authorizer_type = "AWS_IAM"

  # protocol_type is intentionally omitted. AgentCore requires a
  # protocol-less Gateway for HTTP Runtime targets.
  tags = var.tags
}

resource "aws_bedrockagentcore_gateway_target" "runtime" {
  name               = var.target_name
  description        = "AgentCore Runtime exposed through the HTTP Gateway"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    http {
      agentcore_runtime {
        arn       = var.runtime_arn
        qualifier = "DEFAULT"
      }
    }
  }
}

data "aws_iam_policy_document" "runtime_access" {
  statement {
    sid     = "AllowOnlyHttpGateway"
    effect  = "Allow"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]

    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.gateway.arn]
    }

    resources = [var.runtime_arn]
  }

  statement {
    sid     = "DenyDirectInvocation"
    effect  = "Deny"
    actions = ["bedrock-agentcore:InvokeAgentRuntime"]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    resources = [var.runtime_arn]

    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [aws_iam_role.gateway.arn]
    }
  }
}

# Requiring this resource policy's explicit allow prevents callers from
# bypassing the HTTP Gateway and invoking the Runtime directly.
resource "aws_bedrockagentcore_resource_policy" "runtime" {
  resource_arn = var.runtime_arn
  policy       = data.aws_iam_policy_document.runtime_access.json
}
