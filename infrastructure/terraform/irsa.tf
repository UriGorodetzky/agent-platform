# IRSA — give the orchestrator POD its own IAM role (least privilege) instead of
# sharing the node's broad permissions.
#
# Runtime: the pod's ServiceAccount is annotated with this role's ARN; EKS
# projects a signed OIDC token into the pod; the AWS SDK exchanges it via
# STS AssumeRoleWithWebIdentity for temporary credentials scoped to this role.

# --- Register the cluster's OIDC issuer as an IAM identity provider ---
data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
}

# --- Trust policy: ONLY the `default/orchestrator` ServiceAccount may assume it ---
data "aws_iam_policy_document" "orchestrator_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.eks.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(aws_iam_openid_connect_provider.eks.url, "https://", "")}:sub"
      values   = ["system:serviceaccount:default:orchestrator"] # namespace:serviceaccount
    }
  }
}

resource "aws_iam_role" "orchestrator" {
  name               = "${var.project}-orchestrator"
  assume_role_policy = data.aws_iam_policy_document.orchestrator_assume.json
}

# --- Permissions: read/write ONLY our artifacts bucket ---
data "aws_iam_policy_document" "orchestrator_s3" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.artifacts.arn, "${aws_s3_bucket.artifacts.arn}/*"]
  }
}

resource "aws_iam_policy" "orchestrator_s3" {
  name   = "${var.project}-orchestrator-s3"
  policy = data.aws_iam_policy_document.orchestrator_s3.json
}

resource "aws_iam_role_policy_attachment" "orchestrator_s3" {
  role       = aws_iam_role.orchestrator.name
  policy_arn = aws_iam_policy.orchestrator_s3.arn
}
