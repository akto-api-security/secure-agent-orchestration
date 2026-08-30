resource "aws_ecr_repository" "this" {
  name                 = "asl-approval-agent-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}
