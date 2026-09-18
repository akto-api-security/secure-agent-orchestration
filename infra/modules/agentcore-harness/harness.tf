resource "aws_bedrockagentcore_harness" "this" {
  harness_name       = "asl_${var.harness_key}_${var.environment}"
  execution_role_arn = aws_iam_role.harness.arn

  model {
    bedrock_model_config {
      model_id = var.model_id
    }
  }

  system_prompt {
    text = var.system_prompt
  }

  allowed_tools   = ["@${var.gateway_tool_name}/*"]
  max_iterations  = var.max_iterations
  timeout_seconds = var.timeout_seconds

  tool {
    type = "agentcore_gateway"
    name = var.gateway_tool_name

    config {
      agentcore_gateway {
        gateway_arn = var.gateway_arn

        outbound_auth {
          aws_iam = true
        }
      }
    }
  }

  tags = var.tags
}
