# ECR — private Docker registries for our images.
# The CD pipeline pushes here; EKS nodes pull from here (the node IAM role
# already has AmazonEC2ContainerRegistryReadOnly). One repository per image.

locals {
  images = toset(["echo-agent", "agent-orchestrator"])
}

resource "aws_ecr_repository" "app" {
  for_each = local.images

  name = "${var.project}/${each.key}"

  # MUTABLE so our CD's moving `latest` tag can be overwritten. A stricter setup
  # uses IMMUTABLE and references images only by their immutable SHA tag.
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true # scan each pushed image for known vulnerabilities
  }
}

# Keep storage (and cost) down: drop untagged images after a week.
resource "aws_ecr_lifecycle_policy" "app" {
  for_each   = aws_ecr_repository.app
  repository = each.value.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Expire untagged images older than 7 days"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 7
      }
      action = { type = "expire" }
    }]
  })
}
