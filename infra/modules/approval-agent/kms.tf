# Asymmetric signing key for short-lived authorization grants (see
# approval-agent/grants.py). ECC_NIST_P256 / SIGN_VERIFY is ECDSA/SHA-256
# per FIPS 186-4.
#
# No explicit key `policy` -- omitting it gives the provider's documented
# default ("enable IAM User Permissions for this account", i.e. the account
# root gets kms:*), the same pattern this project already uses everywhere
# else (identity-based IAM policies granting specific principals specific
# actions, no custom resource-based policies unless AWS requires one -- see
# the interceptor Lambda module's reasoning for the precedent). The Approval
# Agent's own execution role IAM policy (iam.tf) is what actually grants it
# kms:Sign/kms:Verify on this key.
resource "aws_kms_key" "grants" {
  description              = "Signs/verifies short-lived approval grants for asl-approval-agent-${var.environment}"
  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "ECC_NIST_P256"
  deletion_window_in_days  = 7

  tags = var.tags
}

resource "aws_kms_alias" "grants" {
  name          = "alias/asl-approval-grants-${var.environment}"
  target_key_id = aws_kms_key.grants.key_id
}
