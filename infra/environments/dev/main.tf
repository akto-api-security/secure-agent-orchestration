# No resources yet. Populated in later phases (agents, gateway, policy,
# approval-workflow) via modules under infra/modules/.

locals {
  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
