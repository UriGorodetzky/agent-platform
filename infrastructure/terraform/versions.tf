# Pin the Terraform CLI and provider versions so everyone gets the same behavior.
terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # In production the state lives remotely (shared + locked), e.g.:
  #   backend "s3" { bucket = "...-tfstate" key = "agent-platform" region = "us-east-1" dynamodb_table = "...-locks" }
  # We're not applying, so we leave the default local backend.
}
