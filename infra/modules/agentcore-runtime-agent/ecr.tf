resource "aws_ecr_repository" "this" {
  name                 = "asl-${var.agent_key}-${var.environment}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}
