terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.51"
    }
    # Packages the interceptor Lambda's deployment zip.
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Partial backend configuration: Terraform backend blocks can't reference
  # variables, so "bucket"/"region" (account/deployment-specific) are
  # supplied at `terraform init` time via `-backend-config=backend.hcl`
  # instead (see backend.hcl.example).
  backend "s3" {
    key          = "dev/terraform.tfstate"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}
