# ElastiCache Redis — managed in-memory store for shared, fast, ephemeral state
# (round-robin cursor, circuit-breaker health, locks, caching) across instances.

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-redis"
  subnet_ids = aws_subnet.private[*].id
}

# Firewall: only allow Redis (6379) from inside the VPC.
resource "aws_security_group" "redis" {
  name        = "${var.project}-redis"
  description = "Allow Redis from inside the VPC"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "Redis from within the VPC"
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_elasticache_cluster" "main" {
  cluster_id           = "${var.project}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1 # single node; production uses a replication group w/ failover
  parameter_group_name = "default.redis7"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]
}
