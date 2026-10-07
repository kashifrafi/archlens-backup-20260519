"""Azure Retail Prices API integration for real cost estimates.

Component resolution order (highest priority first):
  1. azure_equivalent – LLM-extracted canonical Azure service name
  2. name             – component name
  3. category / type

Each entry in AZURE_SERVICE_CONFIG maps a normalised key to:
  service_name   – Azure Retail Prices API serviceName
  price_filter   – additional OData $filter fragment (appended to region+consumption base)
  monthly_qty    – assumed quantity per month for cost = unit_price × qty
  unit           – human-readable unit label
"""
import logging
from typing import Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)

_AZURE_PRICES_URL = "https://prices.azure.com/api/retail/prices"

LB_ASSUMPTIONS = {
    "load_balancers": 1,
    "requests_per_second": 50,
    "data_transfer_gb": 100,
    "hours_per_month": 730,
}

# ---------------------------------------------------------------------------
# Config table: normalised key → API query config
# ---------------------------------------------------------------------------
AZURE_SERVICE_CONFIG: Dict[str, Dict] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "virtual machines": {
        "service_name": "Virtual Machines",
        "price_filter": "and contains(meterName, 'B2s') and skuName eq 'B2s'",
        "windows_exclude": True,
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "azure virtual machines": {
        "service_name": "Virtual Machines",
        "price_filter": "and contains(meterName, 'B2s') and skuName eq 'B2s'",
        "windows_exclude": True,
        "monthly_qty": 730, "unit": "1 Hour",
    },
    # ── Database ─────────────────────────────────────────────────────────────
    "azure sql database": {
        # Single Database Standard S0 (small default PaaS database tier)
        "service_name": "SQL Database",
        "price_filter": "and productName eq 'SQL Database Single Standard' and skuName eq 'S0' and meterName eq 'S0 DTUs'",
        "monthly_qty": 30, "unit": "Days (S0 DTU)",
    },
    "sql database": {
        "service_name": "SQL Database",
        "price_filter": "and productName eq 'SQL Database Single Standard' and skuName eq 'S0' and meterName eq 'S0 DTUs'",
        "monthly_qty": 30, "unit": "Days (S0 DTU)",
    },
    "azure database for mysql": {
        # Flexible Server Burstable B1MS — smallest real compute tier
        "service_name": "Azure Database for MySQL",
        "price_filter": "and skuName eq 'B1MS' and contains(productName, 'Burstable')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "azure database for postgresql": {
        # Flexible Server Burstable B1MS
        "service_name": "Azure Database for PostgreSQL",
        "price_filter": "and skuName eq 'B1MS' and contains(productName, 'Burstable')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "azure cosmos db": {
        "service_name": "Azure Cosmos DB",
        "price_filter": "",
        "monthly_qty": 1, "unit": "unit",
    },
    # ── Storage ───────────────────────────────────────────────────────────────
    "azure blob storage": {
        "service_name": "Storage",
        "price_filter": "and skuName eq 'Hot LRS' and contains(productName, 'Blob')",
        "monthly_qty": 100, "unit": "1 GB",
    },
    "storage": {
        "service_name": "Storage",
        "price_filter": "and skuName eq 'Hot LRS' and contains(productName, 'Blob')",
        "monthly_qty": 100, "unit": "1 GB",
    },
    "azure storage": {
        "service_name": "Storage",
        "price_filter": "and skuName eq 'Hot LRS' and contains(productName, 'Blob')",
        "monthly_qty": 100, "unit": "1 GB",
    },
    # ── Functions ─────────────────────────────────────────────────────────────
    "azure functions": {
        "service_name": "Functions",
        "price_filter": "and contains(meterName, 'Execution')",
        "monthly_qty": 1000000, "unit": "1M executions",
    },
    # ── Cache ─────────────────────────────────────────────────────────────────
    "azure cache for redis": {
        "service_name": "Redis Cache",
        "price_filter": "and contains(productName, 'Basic') and contains(skuName, 'C0')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "redis cache": {
        "service_name": "Redis Cache",
        "price_filter": "and contains(productName, 'Basic') and contains(skuName, 'C0')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    # ── Load Balancer ─────────────────────────────────────────────────────────
    # The native Azure Load Balancer hourly rule meter is published under
    # armRegionName='Global' in the Azure Retail Prices API.
    "azure application gateway": {
        "service_name": "Application Gateway",
        "price_filter": "and contains(productName, 'Standard v2') and contains(meterName, 'Fixed')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "application gateway": {
        "service_name": "Application Gateway",
        "price_filter": "and contains(productName, 'Standard v2') and contains(meterName, 'Fixed')",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "azure load balancer": {
        "service_name": "Load Balancer",
        "arm_region": "Global",
        "price_filter": "and productName eq 'Load Balancer' and skuName eq 'Standard' and meterName eq 'Standard Included LB Rules and Outbound Rules'",
        "load_balancer_workload": True,
        "monthly_qty": 1, "unit": "LB workload",
    },
    "load balancer": {
        "service_name": "Load Balancer",
        "arm_region": "Global",
        "price_filter": "and productName eq 'Load Balancer' and skuName eq 'Standard' and meterName eq 'Standard Included LB Rules and Outbound Rules'",
        "load_balancer_workload": True,
        "monthly_qty": 1, "unit": "LB workload",
    },
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "azure kubernetes service": {
        "service_name": "Virtual Machines",
        "price_filter": "and contains(meterName, 'D2s v5') and skuName eq 'Standard_D2s_v5'",
        "windows_exclude": True,
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "azure aks": {
        "service_name": "Virtual Machines",
        "price_filter": "and contains(meterName, 'D2s v5') and skuName eq 'Standard_D2s_v5'",
        "windows_exclude": True,
        "monthly_qty": 730, "unit": "1 Hour",
    },
    # ── Service Bus ───────────────────────────────────────────────────────────
    "azure service bus": {
        "service_name": "Service Bus",
        "price_filter": "",
        "monthly_qty": 1000000, "unit": "1M operations",
    },
    "service bus": {
        "service_name": "Service Bus",
        "price_filter": "", "monthly_qty": 1000000, "unit": "1M operations",
    },
    # ── Event Hubs ────────────────────────────────────────────────────────────
    "azure event hubs": {
        "service_name": "Event Hubs",
        "price_filter": "",
        "monthly_qty": 1, "unit": "unit",
    },
    "azure cdn": {
        "service_name": "Content Delivery Network",
        "price_filter": "and contains(productName, 'Standard Microsoft') and contains(meterName, 'Data Transfer')",
        "monthly_qty": 100, "unit": "1 GB",
    },
    "content delivery network": {
        "service_name": "Content Delivery Network",
        "price_filter": "and contains(productName, 'Standard Microsoft') and contains(meterName, 'Data Transfer')",
        "monthly_qty": 100, "unit": "1 GB",
    },
    "azure app service": {
        "service_name": "Azure App Service",
        "price_filter": "and contains(skuName, 'B2') and priceType eq 'Consumption'",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    "app service": {
        "service_name": "Azure App Service",
        "price_filter": "and contains(skuName, 'B2') and priceType eq 'Consumption'",
        "monthly_qty": 730, "unit": "1 Hour",
    },
    # ── API Management ────────────────────────────────────────────────────────
    "azure api management": {
        "service_name": "API Management",
        "price_filter": "",
        "monthly_qty": 730, "unit": "1 Hour",
    },
}

# Fallback aliases
AZURE_ALIAS_TO_CONFIG_KEY: Dict[str, str] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "compute":                   "virtual machines",
    "vm":                        "virtual machines",
    "virtual machine":           "virtual machines",
    "virtual machines":          "virtual machines",
    "server":                    "virtual machines",
    "web server":                "virtual machines",
    "webserver":                 "virtual machines",
    "app server":                "virtual machines",
    "appserver":                 "virtual machines",
    "container":                 "virtual machines",
    "docker":                    "virtual machines",
    "container apps":            "virtual machines",
    "azure container apps":      "virtual machines",
    # ── Database ─────────────────────────────────────────────────────────────
    "database":                  "azure sql database",
    "sql":                       "azure sql database",
    "azure sql":                 "azure sql database",
    "mysql":                     "azure database for mysql",
    "postgres":                  "azure database for postgresql",
    "postgresql":                "azure database for postgresql",
    "cosmos":                    "azure cosmos db",
    "cosmosdb":                  "azure cosmos db",
    "azure cosmos":              "azure cosmos db",
    # ── Storage ───────────────────────────────────────────────────────────────
    "storage":                   "azure blob storage",
    "blob":                      "azure blob storage",
    "blob storage":              "azure blob storage",
    "azure blob":                "azure blob storage",
    "object storage":            "azure blob storage",
    # ── Serverless / Functions ────────────────────────────────────────────────
    "functions":                 "azure functions",
    "function":                  "azure functions",
    "serverless":                "azure functions",
    "lambda":                    "azure functions",
    # ── Cache ────────────────────────────────────────────────────────────────
    "cache":                     "azure cache for redis",
    "redis":                     "azure cache for redis",
    "azure redis":               "azure cache for redis",
    "redis cache":               "redis cache",
    # ── CDN ──────────────────────────────────────────────────────────────────
    "cdn":                       "azure cdn",
    "cloudfront":                "azure cdn",
    # ── Load Balancing ────────────────────────────────────────────────────────
    "load balancer":             "azure load balancer",
    "loadbalancer":              "azure load balancer",
    "alb":                       "azure load balancer",
    "nlb":                       "azure load balancer",
    "application load balancer": "azure load balancer",
    "network load balancer":     "azure load balancer",
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "kubernetes":                "azure kubernetes service",
    "k8s":                       "azure kubernetes service",
    "aks":                       "azure kubernetes service",
    # ── Messaging / Queue ─────────────────────────────────────────────────────
    "queue":                     "azure service bus",
    "message queue":             "azure service bus",
    "messaging":                 "azure service bus",
    "service bus":               "azure service bus",
    "pubsub":                    "azure service bus",
    # ── API Gateway ───────────────────────────────────────────────────────────
    "api gateway":               "azure api management",
    "apigateway":                "azure api management",
    "gateway":                   "azure api management",
    # ── NoSQL ────────────────────────────────────────────────────────────────
    "nosql":                     "azure cosmos db",
}


def fetch_azure_prices(
    components: List[Dict],
    region: str = "eastus",
) -> Optional[Dict]:
    """Fetch Azure component prices from the Azure Retail Prices API."""
    breakdown = []
    total_monthly = 0.0

    for component in components:
        config_key = _resolve_config_key(component)
        if not config_key:
            logger.debug(f"No Azure config for component: {component.get('name')}")
            continue

        cfg = AZURE_SERVICE_CONFIG[config_key]
        component_display = component.get("name") or config_key

        if cfg.get("load_balancer_workload"):
            lb_price = _load_balancer_workload_price()
            if not lb_price:
                logger.warning(f"Azure: no load balancer workload price for {config_key!r}")
                continue
            breakdown.append({
                "service": cfg["service_name"],
                "component": component_display,
                "monthly_cost": lb_price["monthly_cost"],
                "unit": "1 LB + 50 req/s + 100 GB + 730 hrs",
                "quantity": 1,
                "unit_price": lb_price["monthly_cost"],
            })
            total_monthly += lb_price["monthly_cost"]
            continue

        price_item = _fetch_price_item(cfg, region)
        if not price_item:
            logger.warning(f"Azure: no price for {config_key!r} in {region}")
            continue

        unit_price = float(price_item.get("retailPrice") or 0)
        if unit_price <= 0:
            continue

        qty = cfg["monthly_qty"]
        monthly_cost = round(unit_price * qty, 2)

        breakdown.append({
            "service": price_item.get("serviceName") or cfg["service_name"],
            "component": component_display,
            "monthly_cost": monthly_cost,
            "unit": cfg["unit"],
            "quantity": qty,
            "unit_price": round(unit_price, 8),
        })
        total_monthly += monthly_cost

    return {
        "monthly_estimate": round(total_monthly, 2),
        "annual_estimate": round(total_monthly * 12, 2),
        "currency": "USD",
        "region": region,
        "breakdown": breakdown,
        "assumptions": [
            "Prices from Azure Retail Prices API (Pay-As-You-Go / Consumption)",
            f"Region: {region}",
            "Standard tier SKUs — B2s VM, SQL Database S0, Basic C0 Redis",
            "730 hrs/month for hourly resources; 100 GB for storage",
            "Load Balancer workload: 1 LB, 50 requests/sec, 100 GB/month data processed, 730 hours/month",
        ],
    }


def _load_balancer_workload_price() -> Optional[Dict]:
    hourly_cfg = {
        "service_name": "Load Balancer",
        "arm_region": "Global",
        "price_filter": "and productName eq 'Load Balancer' and skuName eq 'Standard' and meterName eq 'Standard Included LB Rules and Outbound Rules'",
    }
    data_cfg = {
        "service_name": "Load Balancer",
        "arm_region": "Global",
        "price_filter": "and productName eq 'Load Balancer' and skuName eq 'Standard' and meterName eq 'Standard Data Processed'",
    }
    hourly_item = _fetch_price_item(hourly_cfg, "Global")
    data_item = _fetch_price_item(data_cfg, "Global")
    if not hourly_item:
        return None
    hourly_rate = float(hourly_item.get("retailPrice") or 0)
    data_rate = float(data_item.get("retailPrice") or 0) if data_item else 0.0
    monthly_cost = round(
        hourly_rate * LB_ASSUMPTIONS["hours_per_month"] * LB_ASSUMPTIONS["load_balancers"]
        + data_rate * LB_ASSUMPTIONS["data_transfer_gb"],
        2,
    )
    return {"monthly_cost": monthly_cost, "hourly_rate": hourly_rate, "data_gb_rate": data_rate}


def _fetch_price_item(cfg: Dict, region: str) -> Optional[Dict]:
    """Return the cheapest matching price item for the given config + region."""
    extra = cfg.get("price_filter", "")
    arm_region = cfg.get("arm_region", region)
    base = f"armRegionName eq '{arm_region}' and priceType eq 'Consumption' and serviceName eq '{cfg['service_name']}'"
    filt = f"{base} {extra}".strip()
    exclude_kw = cfg.get("exclude_keywords", [])
    try:
        response = httpx.get(_AZURE_PRICES_URL, params={"$filter": filt, "currencyCode": "USD"}, timeout=15.0)
        response.raise_for_status()
        candidates = []
        for item in response.json().get("Items", []):
            product = item.get("productName") or ""
            sku = item.get("skuName") or ""
            if cfg.get("windows_exclude") and "Windows" in product:
                continue
            if any(kw in product or kw in sku for kw in exclude_kw):
                continue
            price = float(item.get("retailPrice") or 0)
            if price > 0:
                candidates.append(item)
        if candidates:
            # Return cheapest option for a fair/conservative comparison
            return min(candidates, key=lambda x: float(x.get("retailPrice") or 0))
    except Exception as e:
        logger.warning(f"Azure Retail Prices API failed: {e}")
    return None


def _resolve_config_key(component: Dict) -> Optional[str]:
    candidates = [
        component.get("azure_equivalent", ""),
        component.get("name", ""),
        component.get("category", ""),
        component.get("type", ""),
    ]
    for candidate in candidates:
        key = str(candidate or "").strip().lower()
        if key in AZURE_SERVICE_CONFIG:
            return key
        if key in AZURE_ALIAS_TO_CONFIG_KEY:
            return AZURE_ALIAS_TO_CONFIG_KEY[key]
    return None


