# Values other configs (and humans) can read after an apply.

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs (for internet-facing load balancers)"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs (for EKS nodes, RDS, Redis)"
  value       = aws_subnet.private[*].id
}
