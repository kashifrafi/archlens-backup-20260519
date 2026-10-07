"""AWS Pricing API integration for real cost estimates.

Component resolution order (highest priority first):
  1. aws_equivalent  – the LLM-extracted canonical AWS service name
  2. name            – component name as typed
  3. category        – broad category (compute / storage / database …)
  4. type            – component type

Each entry in AWS_SERVICE_CONFIG maps a normalised lookup key to a dict with:
  service_code  – AWS Pricing API ServiceCode
  display       – human-readable label used in the breakdown
  filters       – extra TERM_MATCH filters for a standard comparable SKU
  family_filter – productFamily filter (optional, applied instead of extra filters)
  monthly_qty   – assumed monthly quantity (e.g. 730 hrs, 100 GB)
  unit          – unit label for the breakdown
"""
import json
import logging
from typing import Dict, List, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

LB_ASSUMPTIONS = {
    "load_balancers": 1,
    "requests_per_second": 50,
    "data_transfer_gb": 100,
    "hours_per_month": 730,
}

# ---------------------------------------------------------------------------
# Single source-of-truth: normalised key → API query config
# Keys intentionally lowercase; they match values from aws_equivalent / name /
# category / type after .strip().lower().
# ---------------------------------------------------------------------------
AWS_SERVICE_CONFIG: Dict[str, Dict] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "amazon ec2": {
        "service_code": "AmazonEC2", "display": "Amazon EC2",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": "t3.medium"},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
            {"Type": "TERM_MATCH", "Field": "tenancy",         "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw",  "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus",  "Value": "Used"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    "amazon elastic compute cloud": {
        "service_code": "AmazonEC2", "display": "Amazon EC2",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": "t3.medium"},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
            {"Type": "TERM_MATCH", "Field": "tenancy",         "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw",  "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus",  "Value": "Used"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    # ── Database ─────────────────────────────────────────────────────────────
    "amazon rds": {
        "service_code": "AmazonRDS", "display": "Amazon RDS",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": "db.t3.medium"},
            {"Type": "TERM_MATCH", "Field": "databaseEngine",  "Value": "MySQL"},
            {"Type": "TERM_MATCH", "Field": "deploymentOption","Value": "Single-AZ"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    "amazon relational database service": {
        "service_code": "AmazonRDS", "display": "Amazon RDS",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType",    "Value": "db.t3.medium"},
            {"Type": "TERM_MATCH", "Field": "databaseEngine",  "Value": "MySQL"},
            {"Type": "TERM_MATCH", "Field": "deploymentOption","Value": "Single-AZ"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    "amazon dynamodb": {
        "service_code": "AmazonDynamoDB", "display": "Amazon DynamoDB",
        "filters": [],
        "monthly_qty": 1, "unit": "unit",
    },
    "aws dynamodb": {
        "service_code": "AmazonDynamoDB", "display": "Amazon DynamoDB",
        "filters": [], "monthly_qty": 1, "unit": "unit",
    },
    # ── Storage ───────────────────────────────────────────────────────────────
    "amazon s3": {
        "service_code": "AmazonS3", "display": "Amazon S3",
        "filters": [],
        "monthly_qty": 100, "unit": "GB-Mo",
    },
    "amazon simple storage service": {
        "service_code": "AmazonS3", "display": "Amazon S3",
        "filters": [], "monthly_qty": 100, "unit": "GB-Mo",
    },
    "amazon efs": {
        "service_code": "AmazonEFS", "display": "Amazon EFS",
        "filters": [], "monthly_qty": 100, "unit": "GB-Mo",
    },
    "amazon elastic file system": {
        "service_code": "AmazonEFS", "display": "Amazon EFS",
        "filters": [], "monthly_qty": 100, "unit": "GB-Mo",
    },
    # ── Serverless / Functions ────────────────────────────────────────────────
    "aws lambda": {
        "service_code": "AWSLambda", "display": "AWS Lambda",
        "filters": [], "monthly_qty": 1000000, "unit": "requests",
    },
    # ── Cache ─────────────────────────────────────────────────────────────────
    "amazon elasticache": {
        "service_code": "AmazonElastiCache", "display": "Amazon ElastiCache",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "cache.t3.micro"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    "amazon elasticache for redis": {
        "service_code": "AmazonElastiCache", "display": "Amazon ElastiCache",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": "cache.t3.micro"},
        ],
        "monthly_qty": 730, "unit": "Hrs",
    },
    # ── CDN ───────────────────────────────────────────────────────────────────
    "amazon cloudfront": {
        "service_code": "AmazonCloudFront", "display": "Amazon CloudFront",
        "filters": [], "monthly_qty": 100, "unit": "GB",
    },
    "cloudfront": {
        "service_code": "AmazonCloudFront", "display": "Amazon CloudFront",
        "filters": [], "monthly_qty": 100, "unit": "GB",
    },
    # ── Load Balancer ─────────────────────────────────────────────────────────
    "elastic load balancing": {
        "service_code": "AmazonEC2", "display": "Elastic Load Balancing",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
        ],
        "load_balancer_workload": True,
        "monthly_qty": 1, "unit": "LB workload",
    },
    "aws application load balancer": {
        "service_code": "AmazonEC2", "display": "Elastic Load Balancing (ALB)",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
        ],
        "load_balancer_workload": True,
        "monthly_qty": 1, "unit": "LB workload",
    },
    "aws network load balancer": {
        "service_code": "AmazonEC2", "display": "Elastic Load Balancing (NLB)",
        "filters": [
            {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
        ],
        "load_balancer_workload": True,
        "monthly_qty": 1, "unit": "LB workload",
    },
    # ── Message Queue ─────────────────────────────────────────────────────────
    "amazon sqs": {
        "service_code": "AmazonSQS", "display": "Amazon SQS",
        "filters": [], "monthly_qty": 1000000, "unit": "requests",
    },
    "amazon simple queue service": {
        "service_code": "AmazonSQS", "display": "Amazon SQS",
        "filters": [], "monthly_qty": 1000000, "unit": "requests",
    },
    "amazon sns": {
        "service_code": "AmazonSNS", "display": "Amazon SNS",
        "filters": [], "monthly_qty": 1000000, "unit": "requests",
    },
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "amazon eks": {
        "service_code": "AmazonEKS", "display": "Amazon EKS",
        "filters": [], "monthly_qty": 730, "unit": "Hrs",
    },
    "amazon elastic kubernetes service": {
        "service_code": "AmazonEKS", "display": "Amazon EKS",
        "filters": [], "monthly_qty": 730, "unit": "Hrs",
    },
    # ── API Gateway ───────────────────────────────────────────────────────────
    "amazon api gateway": {
        "service_code": "AmazonApiGateway", "display": "Amazon API Gateway",
        "filters": [], "monthly_qty": 1000000, "unit": "requests",
    },
}

# ---------------------------------------------------------------------------
# Fallback aliases: broad category / type / partial name → config key
# Used when the LLM uses a generic term rather than the exact AWS service name.
# ---------------------------------------------------------------------------
AWS_ALIAS_TO_CONFIG_KEY: Dict[str, str] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "compute":                   "amazon elastic compute cloud",
    "ec2":                       "amazon elastic compute cloud",
    "vm":                        "amazon elastic compute cloud",
    "virtual machine":           "amazon elastic compute cloud",
    "server":                    "amazon elastic compute cloud",
    "web server":                "amazon elastic compute cloud",
    "webserver":                 "amazon elastic compute cloud",
    "app server":                "amazon elastic compute cloud",
    "appserver":                 "amazon elastic compute cloud",
    "container":                 "amazon elastic compute cloud",
    "docker":                    "amazon elastic compute cloud",
    "ecs":                       "amazon elastic compute cloud",
    "amazon ecs":                "amazon elastic compute cloud",
    # ── Database ─────────────────────────────────────────────────────────────
    "database":                  "amazon relational database service",
    "rds":                       "amazon relational database service",
    "sql":                       "amazon relational database service",
    "mysql":                     "amazon relational database service",
    "postgres":                  "amazon relational database service",
    "postgresql":                "amazon relational database service",
    # ── Storage ───────────────────────────────────────────────────────────────
    "storage":                   "amazon simple storage service",
    "s3":                        "amazon simple storage service",
    "blob":                      "amazon simple storage service",
    "object storage":            "amazon simple storage service",
    # ── Serverless / Functions ────────────────────────────────────────────────
    "lambda":                    "aws lambda",
    "functions":                 "aws lambda",
    "function":                  "aws lambda",
    "serverless":                "aws lambda",
    # ── Cache ────────────────────────────────────────────────────────────────
    "cache":                     "amazon elasticache",
    "redis":                     "amazon elasticache",
    "elastic cache":             "amazon elasticache",
    "elasticache":               "amazon elasticache",
    "elastic cache for redis":   "amazon elasticache for redis",
    "elasticache for redis":     "amazon elasticache for redis",
    "amazon elasticache redis":  "amazon elasticache for redis",
    "memcached":                 "amazon elasticache",
    # ── CDN ──────────────────────────────────────────────────────────────────
    "cdn":                       "amazon cloudfront",
    "cloudfront":                "amazon cloudfront",
    # ── Load Balancing ────────────────────────────────────────────────────────
    "load balancer":             "elastic load balancing",
    "loadbalancer":              "elastic load balancing",
    "alb":                       "elastic load balancing",
    "nlb":                       "elastic load balancing",
    "elb":                       "elastic load balancing",
    "application load balancer": "elastic load balancing",
    "network load balancer":     "elastic load balancing",
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "kubernetes":                "amazon eks",
    "k8s":                       "amazon eks",
    "aks":                       "amazon eks",
    "eks":                       "amazon eks",
    # ── Messaging / Queue ─────────────────────────────────────────────────────
    "queue":                     "amazon sqs",
    "sqs":                       "amazon sqs",
    "message queue":             "amazon sqs",
    "messaging":                 "amazon sqs",
    "sns":                       "amazon sns",
    "notification":              "amazon sns",
    # ── API Gateway ───────────────────────────────────────────────────────────
    "api gateway":               "amazon api gateway",
    "apigateway":                "amazon api gateway",
    "gateway":                   "amazon api gateway",
    # ── NoSQL ────────────────────────────────────────────────────────────────
    "nosql":                     "amazon dynamodb",
    "dynamodb":                  "amazon dynamodb",
}


def fetch_aws_prices(
    access_key_id: str,
    secret_access_key: str,
    components: List[Dict],
    region: str = "us-east-1",
) -> Optional[Dict]:
    """Fetch real AWS pricing using LLM-extracted aws_equivalent names."""
    try:
        client = boto3.client(
            "pricing",
            region_name="us-east-1",   # Pricing API only available in us-east-1
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
        )

        breakdown = []
        total_monthly = 0.0
        region_name = _get_aws_region_name(region)

        for component in components:
            config_key = _resolve_config_key(component)
            if not config_key:
                logger.debug(f"No AWS config for component: {component.get('name')}")
                continue

            cfg = AWS_SERVICE_CONFIG[config_key]
            service_code = cfg["service_code"]
            display_name = cfg["display"]
            component_display = component.get("name") or config_key

            if cfg.get("load_balancer_workload"):
                lb_price = _load_balancer_workload_price(client, region_name)
                if not lb_price:
                    logger.warning(f"AWS: no load balancer workload price for {display_name}")
                    continue
                breakdown.append({
                    "service": display_name,
                    "component": component_display,
                    "monthly_cost": lb_price["monthly_cost"],
                    "unit": "1 LB + 50 req/s + 100 GB + 730 hrs",
                    "quantity": 1,
                    "unit_price": lb_price["monthly_cost"],
                })
                total_monthly += lb_price["monthly_cost"]
                continue

            filters = [{"Type": "TERM_MATCH", "Field": "location", "Value": region_name}]
            filters.extend(cfg.get("filters", []))

            try:
                response = client.get_products(
                    ServiceCode=service_code, Filters=filters, MaxResults=10)

                price_list = response.get("PriceList", [])
                if not price_list:
                    logger.warning(f"AWS: no products for {display_name} ({service_code})")
                    continue

                unit_price = _best_unit_price(price_list)
                if unit_price <= 0:
                    logger.warning(f"AWS: zero price for {display_name}")
                    continue

                qty = cfg["monthly_qty"]
                monthly_cost = round(unit_price * qty, 2)

                breakdown.append({
                    "service": display_name,
                    "component": component_display,
                    "monthly_cost": monthly_cost,
                    "unit": cfg["unit"],
                    "quantity": qty,
                    "unit_price": round(unit_price, 8),
                })
                total_monthly += monthly_cost
                logger.info(f"AWS {display_name}: ${monthly_cost:.2f}/month")

            except (BotoCoreError, ClientError) as e:
                logger.warning(f"AWS API error for {display_name}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error for {display_name}: {e}")

        return {
            "monthly_estimate": round(total_monthly, 2),
            "annual_estimate": round(total_monthly * 12, 2),
            "currency": "USD",
            "region": region,
            "breakdown": breakdown,
            "assumptions": [
                "Prices from AWS Pricing API (on-demand, Linux)",
                f"Region: {region_name}",
                "Standard tier SKUs — t3.medium compute, db.t3.medium RDS, cache.t3.micro ElastiCache",
                "730 hrs/month for hourly resources; 100 GB for storage",
                "Load Balancer workload: 1 LB, 50 requests/sec, 100 GB/month data processed, 730 hours/month",
            ],
        }

    except Exception as e:
        logger.error(f"Error fetching AWS pricing: {e}")
        return None


def _get_aws_region_name(region_code: str) -> str:
    region_map = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-central-1": "EU (Frankfurt)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-southeast-2": "Asia Pacific (Sydney)",
        "ap-northeast-1": "Asia Pacific (Tokyo)",
    }
    return region_map.get(region_code, "US East (N. Virginia)")


def _resolve_config_key(component: Dict) -> Optional[str]:
    """
    Try each candidate in priority order:
      1. aws_equivalent (LLM-extracted canonical AWS service name)
      2. component name
    3. type
    4. category
    Check exact match in AWS_SERVICE_CONFIG first, then alias table.
    """
    candidates = [
        component.get("aws_equivalent", ""),
        component.get("name", ""),
        component.get("type", ""),
        component.get("category", ""),
    ]
    for candidate in candidates:
        key = str(candidate or "").strip().lower()
        if key in AWS_SERVICE_CONFIG:
            return key
        if key in AWS_ALIAS_TO_CONFIG_KEY:
            return AWS_ALIAS_TO_CONFIG_KEY[key]
    return None


def _best_unit_price(price_list: List[str]) -> float:
    """Extract the lowest non-zero USD unit price from the first few products."""
    for raw in price_list[:5]:
        try:
            data = json.loads(raw)
            on_demand = data.get("terms", {}).get("OnDemand", {})
            for term in on_demand.values():
                for dim in term.get("priceDimensions", {}).values():
                    usd = float((dim.get("pricePerUnit") or {}).get("USD", "0") or "0")
                    if usd > 0:
                        return usd
        except Exception:
            continue
    return 0.0


def _price_from_products(price_list: List[str], text_matches: List[str]) -> float:
    for raw in price_list:
        try:
            data = json.loads(raw)
            attrs = data.get("product", {}).get("attributes", {})
            haystack = " ".join(str(attrs.get(k, "")) for k in ("usagetype", "operation", "group", "groupDescription", "description")).lower()
            if not all(match.lower() in haystack for match in text_matches):
                continue
            on_demand = data.get("terms", {}).get("OnDemand", {})
            for term in on_demand.values():
                for dim in term.get("priceDimensions", {}).values():
                    usd = float((dim.get("pricePerUnit") or {}).get("USD", "0") or "0")
                    if usd > 0:
                        return usd
        except Exception:
            continue
    return 0.0


def _load_balancer_workload_price(client, region_name: str) -> Optional[Dict]:
    filters = [
        {"Type": "TERM_MATCH", "Field": "location", "Value": region_name},
        {"Type": "TERM_MATCH", "Field": "productFamily", "Value": "Load Balancer"},
    ]
    response = client.get_products(ServiceCode="AmazonEC2", Filters=filters, MaxResults=100)
    products = response.get("PriceList", [])
    hourly = _price_from_products(products, ["loadbalancerusage"])
    data_gb = _price_from_products(products, ["dataprocessing", "bytes"])
    if not hourly:
        return None
    monthly_cost = round(
        hourly * LB_ASSUMPTIONS["hours_per_month"] * LB_ASSUMPTIONS["load_balancers"]
        + data_gb * LB_ASSUMPTIONS["data_transfer_gb"],
        2,
    )
    return {"monthly_cost": monthly_cost, "hourly_rate": hourly, "data_gb_rate": data_gb}
