# The network everything else sits inside.
#
# Layout (2 availability zones for HA):
#   public  subnets → internet-facing things (load balancers, the NAT gateway)
#   private subnets → the workloads (EKS nodes, RDS, Redis) — no inbound internet
#
#   internet ⇄ Internet Gateway ⇄ public subnets
#                                      │ (NAT)
#   private subnets ──outbound only──►─┘──► internet   (pull images, call APIs)

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true # needed so EKS/RDS get DNS names
  tags                 = { Name = "${var.project}-vpc" }
}

# --- Subnets: one public + one private per availability zone ---

resource "aws_subnet" "public" {
  count                   = length(var.azs)
  vpc_id                  = aws_vpc.main.id
  availability_zone       = var.azs[count.index]
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, count.index) # 10.0.0.0/24, 10.0.1.0/24
  map_public_ip_on_launch = true                                     # instances here get a public IP
  tags = {
    Name                     = "${var.project}-public-${count.index}"
    "kubernetes.io/role/elb" = "1" # EKS puts public load balancers in these
  }
}

resource "aws_subnet" "private" {
  count             = length(var.azs)
  vpc_id            = aws_vpc.main.id
  availability_zone = var.azs[count.index]
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, count.index + 10) # 10.0.10.0/24, 10.0.11.0/24
  tags = {
    Name                              = "${var.project}-private-${count.index}"
    "kubernetes.io/role/internal-elb" = "1" # EKS puts internal load balancers here
  }
}

# --- Internet Gateway: the VPC's door to the public internet ---

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project}-igw" }
}

# --- NAT Gateway: lets PRIVATE workloads reach OUT (but not be reached IN) ---
# NOTE: a NAT gateway costs ~$32/mo + data. Production HA runs one per AZ; we
# use a single one here to keep it simple (and cheap, if this were applied).

resource "aws_eip" "nat" {
  domain = "vpc"
  tags   = { Name = "${var.project}-nat-eip" }
}

resource "aws_nat_gateway" "main" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id # the NAT lives in a public subnet
  tags          = { Name = "${var.project}-nat" }
  depends_on    = [aws_internet_gateway.main]
}

# --- Route tables: the rules that decide where traffic goes ---

# Public: send "everything else" (0.0.0.0/0) straight to the internet gateway.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
  tags = { Name = "${var.project}-public-rt" }
}

resource "aws_route_table_association" "public" {
  count          = length(aws_subnet.public)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# Private: send "everything else" to the NAT gateway (outbound-only internet).
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.main.id
  }
  tags = { Name = "${var.project}-private-rt" }
}

resource "aws_route_table_association" "private" {
  count          = length(aws_subnet.private)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
