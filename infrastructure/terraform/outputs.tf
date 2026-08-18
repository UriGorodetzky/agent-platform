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

output "eks_cluster_name" {
  description = "Name of the EKS cluster (use with: aws eks update-kubeconfig)"
  value       = aws_eks_cluster.main.name
}

output "eks_cluster_endpoint" {
  description = "The Kubernetes API endpoint"
  value       = aws_eks_cluster.main.endpoint
}

output "ecr_repository_urls" {
  description = "Push/pull URLs for each image repository"
  value       = { for name, repo in aws_ecr_repository.app : name => repo.repository_url }
}

output "rds_endpoint" {
  description = "PostgreSQL host (the app connects here instead of a SQLite file)"
  value       = aws_db_instance.main.address
}

output "redis_endpoint" {
  description = "Redis host for shared ephemeral state"
  value       = aws_elasticache_cluster.main.cache_nodes[0].address
}

output "s3_bucket" {
  description = "Bucket for large artifacts"
  value       = aws_s3_bucket.artifacts.bucket
}
