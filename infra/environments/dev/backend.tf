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

  backend "s3" {
    # Bucket name must match the "state_bucket_name" output from
    # infra/bootstrap (agent-security-lab-tfstate-<account_id>).
    bucket       = "agent-security-lab-tfstate-000000000000"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region
}
