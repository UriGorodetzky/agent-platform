# Inputs — override these per environment (dev/staging/prod) without editing code.

variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix applied to every resource"
  type        = string
  default     = "agent-platform"
}

variable "vpc_cidr" {
  description = "IP range for the whole VPC"
  type        = string
  default     = "10.0.0.0/16" # 65,536 addresses to carve subnets from
}

variable "azs" {
  description = "Availability zones to spread across (for high availability)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "db_username" {
  description = "Master username for the RDS database"
  type        = string
  default     = "orchestrator"
}

variable "db_password" {
  description = "Master password for RDS — supply via TF_VAR_db_password; never commit"
  type        = string
  sensitive   = true # Terraform hides this in plan/output
  # No default on purpose: it must be provided (kept out of code, like our other secrets).
}
