resource "aws_bedrockagentcore_gateway" "this" {
  name     = "asl-gateway-${var.environment}"
  role_arn = aws_iam_role.gateway.arn

  authorizer_type = "AWS_IAM"
  protocol_type   = "MCP"

  # REQUEST-only interceptor (see gateway-interceptor module). RESPONSE
  # isn't configured -- the goal here is blocking before the MCP target
  # runs, not response transformation/redaction. Confirmed against AWS docs
  # that a gateway can carry one REQUEST + one RESPONSE interceptor at
  # most.
  dynamic "interceptor_configuration" {
    for_each = var.enable_interceptor ? [1] : []
    content {
      interception_points = ["REQUEST"]
      interceptor {
        lambda {
          arn = var.interceptor_lambda_arn
        }
      }
      input_configuration {
        pass_request_headers = false
      }
    }
  }

  tags = var.tags
}

# Two explicit targets rather than a for_each loop: the architecture doc
# names these two MCP servers individually (mac-akto-api-mcp,
# mac-akto-ai-mcp) and there are exactly two, so a loop would add indirection
# without removing any duplication. Both require no outbound authentication
# (confirmed by direct, unauthenticated tools/list probe against each
# endpoint) so credential_provider_configuration is intentionally omitted.
resource "aws_bedrockagentcore_gateway_target" "api_docs" {
  name               = "mac-akto-api-mcp"
  description        = "Akto API Security documentation MCP server"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id

  target_configuration {
    mcp {
      mcp_server {
        endpoint = var.mcp_targets["mac-akto-api-mcp"].endpoint
      }
    }
  }
}

resource "aws_bedrockagentcore_gateway_target" "ai_docs" {
  name               = "mac-akto-ai-mcp"
  description        = "Akto AI Security documentation MCP server"
  gateway_identifier = aws_bedrockagentcore_gateway.this.gateway_id

  target_configuration {
    mcp {
      mcp_server {
        endpoint = var.mcp_targets["mac-akto-ai-mcp"].endpoint
      }
    }
  }
}
