"""
module_registry.py — Terraform community module catalogue with live version pinning.

Fetches the latest stable version of each terraform-aws-modules/* module from
the Terraform Registry API and builds the source/version strings used in prompts.

Modules are cached in-process (refreshed once per hour) so generation stays fast.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_REGISTRY = "https://registry.terraform.io"
_CACHE: Dict[str, Tuple[str, float]] = {}   # module_key → (version, ts)
_TTL = 3600  # seconds


def _fetch_latest_version(namespace: str, module: str, provider: str) -> Optional[str]:
    try:
        url = f"{_REGISTRY}/v1/modules/{namespace}/{module}/{provider}"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "ArchLens/1.0"})
        resp.raise_for_status()
        return resp.json().get("version")
    except Exception as exc:
        logger.warning("module_registry: could not fetch %s/%s/%s — %s", namespace, module, provider, exc)
        return None


def get_module_version(namespace: str, module: str, provider: str = "aws") -> str:
    """Return a known-good pinned version compatible with hashicorp/aws ~> 5.0.

    Pinned versions in _FALLBACK_VERSIONS always take precedence over the live
    registry response, because many module latest releases now require aws >= 6.x
    which is incompatible with the ~> 5.0 provider constraint we generate.
    """
    key = f"{namespace}/{module}/{provider}"
    # Pinned versions take priority — live registry may return aws-6.x incompatible versions
    if key in _FALLBACK_VERSIONS:
        return _FALLBACK_VERSIONS[key]
    now = time.time()
    if key in _CACHE and now - _CACHE[key][1] < _TTL:
        return _CACHE[key][0]
    ver = _fetch_latest_version(namespace, module, provider)
    if ver:
        _CACHE[key] = (ver, now)
        return ver
    return "latest"


_FALLBACK_VERSIONS: Dict[str, str] = {
    "terraform-aws-modules/vpc/aws":             "5.17.0",
    "terraform-aws-modules/ec2-instance/aws":    "5.7.1",
    "terraform-aws-modules/rds/aws":             "6.10.0",
    "terraform-aws-modules/s3-bucket/aws":       "4.2.2",
    "terraform-aws-modules/alb/aws":             "9.11.0",
    "terraform-aws-modules/eks/aws":             "20.36.0",
    "terraform-aws-modules/iam/aws":             "5.48.0",
    "terraform-aws-modules/security-group/aws":  "5.2.0",
    "terraform-aws-modules/acm/aws":             "5.1.1",
    "terraform-aws-modules/cloudfront/aws":      "4.0.0",
    "terraform-aws-modules/lambda/aws":          "7.20.1",
    "terraform-aws-modules/elasticache/aws":     "1.4.1",
    "terraform-aws-modules/autoscaling/aws":     "8.3.1",
    "terraform-aws-modules/sqs/aws":             "4.2.1",
    "terraform-aws-modules/sns/aws":             "6.4.0",
    "terraform-aws-modules/kms/aws":             "3.1.1",
}


# ── Module catalogue ──────────────────────────────────────────────────────────
# Maps a logical component type → (namespace, module, provider, key_inputs doc)

AWS_MODULES: Dict[str, Dict] = {
    "vpc": {
        "namespace": "terraform-aws-modules",
        "module":    "vpc",
        "provider":  "aws",
        "source":    "terraform-aws-modules/vpc/aws",
        "doc": """
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "{version}"

  name = var.vpc_name
  cidr = var.vpc_cidr  # e.g. "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b", "us-east-1c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = false   # true for dev, false for HA prod
  one_nat_gateway_per_az = true

  enable_dns_hostnames = true
  enable_dns_support   = true

  # NACLs are managed by the module
  public_dedicated_network_acl  = true
  private_dedicated_network_acl = true

  # VPC Flow Logs
  enable_flow_log                      = true
  create_flow_log_cloudwatch_log_group = true
  create_flow_log_cloudwatch_iam_role  = true
  flow_log_max_aggregation_interval    = 60

  tags = var.common_tags
}""",
    },
    "ec2": {
        "namespace": "terraform-aws-modules",
        "module":    "ec2-instance",
        "provider":  "aws",
        "source":    "terraform-aws-modules/ec2-instance/aws",
        "doc": """
module "ec2" {
  source  = "terraform-aws-modules/ec2-instance/aws"
  version = "{version}"

  name          = var.ec2_name
  instance_type = var.instance_type   # e.g. "t3.micro"
  ami           = var.ami_id           # data source recommended

  subnet_id              = module.vpc.private_subnets[0]
  vpc_security_group_ids = [module.security_group.security_group_id]
  iam_instance_profile   = aws_iam_instance_profile.ec2.name

  associate_public_ip_address = false
  monitoring                  = true

  root_block_device = [{
    volume_type           = "gp3"
    volume_size           = 30
    encrypted             = true
    delete_on_termination = true
  }]

  tags = var.common_tags
}""",
    },
    "rds": {
        "namespace": "terraform-aws-modules",
        "module":    "rds",
        "provider":  "aws",
        "source":    "terraform-aws-modules/rds/aws",
        "doc": """
module "rds" {
  source  = "terraform-aws-modules/rds/aws"
  version = "{version}"

  identifier = var.db_identifier

  engine               = "mysql"       # or postgres, mariadb, etc.
  engine_version       = "8.0"
  instance_class       = var.db_instance_class
  allocated_storage    = 20
  max_allocated_storage = 100

  db_name  = var.db_name
  username = var.db_username
  port     = 3306

  # Credentials — use Secrets Manager in production
  manage_master_user_password = true

  multi_az               = true
  db_subnet_group_name   = module.vpc.database_subnet_group
  vpc_security_group_ids = [module.rds_sg.security_group_id]

  storage_encrypted   = true
  deletion_protection = true
  skip_final_snapshot = false
  backup_retention_period = 7

  performance_insights_enabled = true

  tags = var.common_tags
}""",
    },
    "s3": {
        "namespace": "terraform-aws-modules",
        "module":    "s3-bucket",
        "provider":  "aws",
        "source":    "terraform-aws-modules/s3-bucket/aws",
        "doc": """
module "s3_bucket" {
  source  = "terraform-aws-modules/s3-bucket/aws"
  version = "{version}"

  bucket = var.bucket_name

  # Block all public access
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  versioning = {
    enabled = true
  }

  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        sse_algorithm = "aws:kms"
      }
      bucket_key_enabled = true
    }
  }

  logging = {
    target_bucket = module.s3_logs.s3_bucket_id
    target_prefix = "s3-access-logs/"
  }

  tags = var.common_tags
}""",
    },
    "alb": {
        "namespace": "terraform-aws-modules",
        "module":    "alb",
        "provider":  "aws",
        "source":    "terraform-aws-modules/alb/aws",
        "doc": """
module "alb" {
  source  = "terraform-aws-modules/alb/aws"
  version = "{version}"

  name    = var.alb_name
  vpc_id  = module.vpc.vpc_id
  subnets = module.vpc.public_subnets

  # Security
  security_groups = [module.alb_sg.security_group_id]
  enable_deletion_protection = true

  access_logs = {
    bucket  = module.s3_logs.s3_bucket_id
    prefix  = "alb-logs"
    enabled = true
  }

  target_groups = {
    main = {
      name             = "${var.project}-tg"
      protocol         = "HTTP"
      port             = 80
      target_type      = "ip"
      health_check = {
        enabled             = true
        path                = "/health"
        healthy_threshold   = 2
        unhealthy_threshold = 3
      }
    }
  }

  listeners = {
    http_redirect = {
      port     = 80
      protocol = "HTTP"
      redirect = {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
    https = {
      port            = 443
      protocol        = "HTTPS"
      certificate_arn = var.acm_certificate_arn
      forward = {
        target_group_key = "main"
      }
    }
  }

  tags = var.common_tags
}""",
    },
    "security_group": {
        "namespace": "terraform-aws-modules",
        "module":    "security-group",
        "provider":  "aws",
        "source":    "terraform-aws-modules/security-group/aws",
        "doc": """
module "security_group" {
  source  = "terraform-aws-modules/security-group/aws"
  version = "{version}"

  name        = var.sg_name
  description = var.sg_description
  vpc_id      = module.vpc.vpc_id

  ingress_cidr_blocks = ["10.0.0.0/8"]
  ingress_rules       = ["https-443-tcp", "http-80-tcp"]
  egress_rules        = ["all-all"]

  tags = var.common_tags
}""",
    },
    "eks": {
        "namespace": "terraform-aws-modules",
        "module":    "eks",
        "provider":  "aws",
        "source":    "terraform-aws-modules/eks/aws",
        "doc": """
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "{version}"

  cluster_name    = var.cluster_name
  cluster_version = "1.31"

  vpc_id                   = module.vpc.vpc_id
  subnet_ids               = module.vpc.private_subnets
  control_plane_subnet_ids = module.vpc.intra_subnets

  cluster_endpoint_public_access  = true
  cluster_endpoint_private_access = true

  enable_cluster_creator_admin_permissions = true

  cluster_addons = {
    coredns                = { most_recent = true }
    kube-proxy             = { most_recent = true }
    vpc-cni                = { most_recent = true }
    aws-ebs-csi-driver     = { most_recent = true }
  }

  eks_managed_node_groups = {
    main = {
      instance_types = [var.node_instance_type]
      min_size       = 1
      max_size       = 5
      desired_size   = 2
      disk_size      = 50
    }
  }

  tags = var.common_tags
}""",
    },
    "lambda": {
        "namespace": "terraform-aws-modules",
        "module":    "lambda",
        "provider":  "aws",
        "source":    "terraform-aws-modules/lambda/aws",
        "doc": """
module "lambda" {
  source  = "terraform-aws-modules/lambda/aws"
  version = "{version}"

  function_name = var.lambda_function_name
  description   = var.lambda_description
  handler       = "index.handler"
  runtime       = "python3.12"

  source_path = "${path.module}/src"

  vpc_subnet_ids         = module.vpc.private_subnets
  vpc_security_group_ids = [module.lambda_sg.security_group_id]
  attach_network_policy  = true

  environment_variables = {
    ENVIRONMENT = var.environment
  }

  cloudwatch_logs_retention_in_days = 14

  tags = var.common_tags
}""",
    },
    "autoscaling": {
        "namespace": "terraform-aws-modules",
        "module":    "autoscaling",
        "provider":  "aws",
        "source":    "terraform-aws-modules/autoscaling/aws",
        "doc": """
module "autoscaling" {
  source  = "terraform-aws-modules/autoscaling/aws"
  version = "{version}"

  name = var.asg_name

  min_size         = 1
  max_size         = var.asg_max_size
  desired_capacity = var.asg_desired

  vpc_zone_identifier = module.vpc.private_subnets

  # Launch template (NOT launch_configuration — removed in AWS provider v5)
  image_id      = var.ami_id
  instance_type = var.instance_type

  security_groups = [module.security_group.security_group_id]

  enable_monitoring = true

  block_device_mappings = [
    {
      device_name = "/dev/xvda"
      ebs = {
        volume_size           = 30
        volume_type           = "gp3"
        encrypted             = true
        delete_on_termination = true
      }
    }
  ]

  target_group_arns = [module.alb.target_groups["main"].arn]

  tags = var.common_tags
}""",
    },
    "kms": {
        "namespace": "terraform-aws-modules",
        "module":    "kms",
        "provider":  "aws",
        "source":    "terraform-aws-modules/kms/aws",
        "doc": """
module "kms" {
  source  = "terraform-aws-modules/kms/aws"
  version = "{version}"

  description = var.kms_description
  key_usage   = "ENCRYPT_DECRYPT"

  enable_key_rotation     = true
  rotation_period_in_days = 365
  deletion_window_in_days = 30

  # Aliases
  aliases = ["${var.project}/${var.environment}"]

  tags = var.common_tags
}""",
    },
    "acm": {
        "namespace": "terraform-aws-modules",
        "module":    "acm",
        "provider":  "aws",
        "source":    "terraform-aws-modules/acm/aws",
        "doc": """
module "acm" {
  source  = "terraform-aws-modules/acm/aws"
  version = "{version}"

  domain_name  = var.domain_name
  zone_id      = var.route53_zone_id

  subject_alternative_names = [
    "*.${var.domain_name}",
  ]

  wait_for_validation = true
  tags = var.common_tags
}""",
    },
}


def build_module_catalogue(cloud: str = "aws") -> str:
    """
    Build a prompt-ready module catalogue with pinned versions.
    Returns a multi-line string describing all available community modules.
    """
    if cloud != "aws":
        return ""   # Azure/GCP module catalogue not yet implemented

    lines = [
        "AVAILABLE TERRAFORM COMMUNITY MODULES (terraform-aws-modules — use these INSTEAD of raw resources):\n"
    ]
    for key, meta in AWS_MODULES.items():
        ver = get_module_version(meta["namespace"], meta["module"], meta["provider"])
        doc = meta["doc"].replace("{version}", ver)
        lines.append(f"### {key.upper()} MODULE  (source: {meta['source']}, version: {ver})")
        lines.append(doc)
        lines.append("")

    return "\n".join(lines)


def get_module_sources(cloud: str = "aws") -> Dict[str, str]:
    """Return {module_key: 'source/version'} dict for required_providers block."""
    if cloud != "aws":
        return {}
    result = {}
    for key, meta in AWS_MODULES.items():
        ver = get_module_version(meta["namespace"], meta["module"], meta["provider"])
        result[key] = f'{meta["source"]}  # {ver}'
    return result
