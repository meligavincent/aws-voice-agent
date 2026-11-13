terraform {
  required_version = ">= 1.10, < 2.0"
  backend "s3" {}
  required_providers { aws = { source = "hashicorp/aws", version = "~> 6.69" } }
}
provider "aws" {
  region              = var.primary_region
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = var.name, ManagedBy = "Terraform", Environment = var.environment } }
}
provider "aws" {
  alias               = "standby"
  region              = var.standby_region
  allowed_account_ids = [var.account_id]
  default_tags { tags = { Project = var.name, ManagedBy = "Terraform", Environment = var.environment } }
}
