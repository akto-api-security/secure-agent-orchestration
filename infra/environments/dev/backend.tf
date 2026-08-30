terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.51"
    }
    # Phase 4: packages the interceptor Lambda's deployment zip
    # (infra/modules/gateway-interceptor/lambda.tf).
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }

  # Phase 6: partial backend configuration. Terraform backend blocks can
  # never reference variables, so "bucket"/"region" -- both account/
  # deployment-specific -- are supplied at `terraform init` time via
  # `-backend-config=backend.hcl` instead of being literal here (the one
  # hardcoded account ID this repo had -- see docs/portability-notes.md).
  # See backend.hcl.example for the file to copy and fill in; the real
  # backend.hcl is gitignored (account-specific, generated locally from
  # infra/bootstrap's `state_bucket_name` output -- scripts/bootstrap.sh
  # does this for you).
  backend "s3" {
    key          = "dev/terraform.tfstate"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}
