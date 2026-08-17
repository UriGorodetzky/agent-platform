# The AWS provider — the plugin that talks to the AWS API.
# Credentials are NOT here; Terraform picks them up from the environment
# (env vars, ~/.aws/credentials, or an IAM role). That keeps secrets out of code.
provider "aws" {
  region = var.region

  # Tag everything automatically, so every resource is traceable to this project.
  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
