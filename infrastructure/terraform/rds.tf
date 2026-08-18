# RDS PostgreSQL — the managed relational database that replaces SQLite.

# Which subnets the DB may live in (the private ones — no internet exposure).
resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db"
  subnet_ids = aws_subnet.private[*].id
}

# A firewall around the DB: only allow Postgres (5432) from inside the VPC.
resource "aws_security_group" "rds" {
  name        = "${var.project}-rds"
  description = "Allow Postgres from inside the VPC"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "PostgreSQL from within the VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr] # tighter: reference the EKS node security group
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_instance" "main" {
  identifier     = "${var.project}-db"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_encrypted = true

  db_name  = "orchestrator"
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  publicly_accessible    = false # never expose the DB to the internet

  multi_az            = false # single-AZ for cost; production sets multi_az = true
  skip_final_snapshot = true  # non-prod convenience
}
