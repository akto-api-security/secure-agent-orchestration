output "state_bucket_name" {
  description = "Name of the S3 bucket holding Terraform state. Referenced by infra/environments/*/backend.tf."
  value       = aws_s3_bucket.tf_state.id
}
