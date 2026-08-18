# EKS — managed Kubernetes on top of our VPC.
#
# AWS runs the control plane (API server, etcd, scheduler); we supply the worker
# nodes (a managed node group of EC2 instances). Our k8s/ manifests would run
# here unchanged.

# ---------------------------------------------------------------------------
# IAM role for the CONTROL PLANE (lets EKS act on our behalf, e.g. make LBs).
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "eks_cluster_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"] # only the EKS service may assume this role
    }
  }
}

resource "aws_iam_role" "cluster" {
  name               = "${var.project}-eks-cluster"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume.json
}

resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy" # AWS-managed policy
}

# ---------------------------------------------------------------------------
# The cluster (control plane).
# ---------------------------------------------------------------------------
resource "aws_eks_cluster" "main" {
  name     = var.project
  role_arn = aws_iam_role.cluster.arn
  version  = "1.31"

  vpc_config {
    # Give EKS both subnet tiers: public for internet-facing LBs, private for nodes.
    subnet_ids = concat(aws_subnet.public[*].id, aws_subnet.private[*].id)
  }

  depends_on = [aws_iam_role_policy_attachment.cluster]
}

# ---------------------------------------------------------------------------
# IAM role for the WORKER NODES (join cluster + pod networking + pull from ECR).
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "eks_node_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"] # the EC2 nodes assume this role
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${var.project}-eks-node"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume.json
}

# The three policies every EKS node needs:
resource "aws_iam_role_policy_attachment" "node_worker" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy" # join the cluster
}

resource "aws_iam_role_policy_attachment" "node_cni" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy" # give pods VPC IPs
}

resource "aws_iam_role_policy_attachment" "node_ecr" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly" # pull images
}

# ---------------------------------------------------------------------------
# Managed node group: the EC2 workers that actually run the pods.
# ---------------------------------------------------------------------------
resource "aws_eks_node_group" "main" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project}-nodes"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = aws_subnet.private[*].id # nodes live in PRIVATE subnets

  instance_types = ["t3.medium"]

  scaling_config {
    desired_size = 2
    min_size     = 2
    max_size     = 4
  }

  # Don't create nodes until their permissions exist, or they can't join.
  depends_on = [
    aws_iam_role_policy_attachment.node_worker,
    aws_iam_role_policy_attachment.node_cni,
    aws_iam_role_policy_attachment.node_ecr,
  ]
}
