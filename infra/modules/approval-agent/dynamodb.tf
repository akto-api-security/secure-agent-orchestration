# One item per approval/HITL request, keyed by reference_id (the
# interceptor's approval_id/hitl_id -- see approval-agent/state.py).
# PAY_PER_REQUEST: request volume here is low/spiky (a human deciding),
# with no capacity-planning benefit from provisioned throughput. TTL is
# hygiene/cleanup only -- the authoritative expiry check is
# application-level (grants.py, state.py), since DynamoDB's own TTL
# deletion is best-effort and can lag.
resource "aws_dynamodb_table" "approval_state" {
  name         = "asl-approval-workflow-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "reference_id"

  attribute {
    name = "reference_id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  tags = var.tags
}
