"""GCP Pricing API integration using the public Cloud Billing Catalog REST API.

Component resolution order:
  1. gcp_equivalent – LLM-extracted canonical GCP service name
  2. name / category / type

Each GCP_SERVICE_CONFIG entry maps a normalised key to:
  catalog_display  – displayName in the GCP Billing Catalog
  catalog_id       – service ID (e.g. services/95FF-2EF5-5EA1)
                     Used when displayName lookup would be ambiguous
  sku_selector     – callable(api_key, service_name, region) -> Optional[Dict]
                     Returns {"unit_price": float, "unit": str}
  monthly_qty      – assumed monthly quantity
  unit_label       – human-readable unit for the breakdown
"""
import logging
from typing import Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)
CATALOG_BASE_URL = "https://cloudbilling.googleapis.com/v1"

LB_ASSUMPTIONS = {
    "load_balancers": 1,
    "requests_per_second": 50,
    "data_transfer_gb": 100,
    "hours_per_month": 730,
}

# ---------------------------------------------------------------------------
# Low-level SKU helpers
# ---------------------------------------------------------------------------

def _money_to_float(money: Dict) -> float:
    return float(money.get("units") or 0) + float(money.get("nanos") or 0) / 1_000_000_000


def _sku_usd_price(sku: Dict) -> Optional[float]:
    for pi in sku.get("pricingInfo", []):
        for tier in pi.get("pricingExpression", {}).get("tieredRates", []):
            money = tier.get("unitPrice", {})
            if money.get("currencyCode") == "USD":
                p = _money_to_float(money)
                if p > 0:
                    return p
    return None


def _list_skus(api_key: str, service_name: str) -> List[Dict]:
    skus: List[Dict] = []
    page_token = None
    while True:
        params = {"key": api_key}
        if page_token:
            params["pageToken"] = page_token
        r = httpx.get(f"{CATALOG_BASE_URL}/{service_name}/skus", params=params, timeout=25.0)
        r.raise_for_status()
        data = r.json()
        skus.extend(data.get("skus", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            return skus


# ---------------------------------------------------------------------------
# Per-service SKU selectors
# ---------------------------------------------------------------------------

def _sku_e2_medium(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """e2-medium = 2 vCPU + 4 GB RAM; combine core + RAM on-demand SKUs."""
    core_price = ram_price = None
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        regions = sku.get("serviceRegions", [])
        if region not in regions and "global" not in regions:
            continue
        if any(bad in desc for bad in ("Spot", "Preemptible", "Commitment", "Committed")):
            continue
        price = _sku_usd_price(sku)
        if not price:
            continue
        if desc == "E2 Instance Core running in Americas":
            core_price = price
        elif desc == "E2 Instance Ram running in Americas":
            ram_price = price
        if core_price is not None and ram_price is not None:
            return {"unit_price": round(core_price * 2 + ram_price * 4, 9), "unit": "h"}
    return None


def _sku_cloud_sql_mysql_small(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """db-f1-micro or db-g1-small MySQL in the target region."""
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        regions = sku.get("serviceRegions", [])
        if region not in regions and "global" not in regions:
            continue
        if "MySQL" not in desc and "Zonal" not in desc and "Regional" not in desc:
            continue
        if any(bad in desc for bad in ("Replica", "HA", "Commitment", "Committed")):
            continue
        price = _sku_usd_price(sku)
        if price:
            return {"unit_price": price, "unit": "h"}
    return None


def _sku_cloud_storage_standard(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """Standard storage at rest in the target region."""
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        regions = sku.get("serviceRegions", [])
        if region not in regions and "global" not in regions:
            continue
        if "Standard Storage" not in desc and "Multi-Regional Storage" not in desc:
            continue
        price = _sku_usd_price(sku)
        if price:
            return {"unit_price": price, "unit": "GiBy.mo"}
    return None


def _sku_networking_lb_forwarding_rule(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """Cloud Load Balancing workload: forwarding rule hours + data processing."""
    hourly_price = None
    data_price = None
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        regions = sku.get("serviceRegions", [])
        if region not in regions and "global" not in regions:
            continue
        price = _sku_usd_price(sku)
        if not price:
            continue
        if hourly_price is None and (
            desc == "Cloud Load Balancer Forwarding Rule Minimum Global"
            or desc == "Cloud Load Balancer Forwarding Rule Minimum for Americas (multi-region)"
            or "Regional External Application Load Balancer Forwarding Rule Minimum" in desc
        ):
            hourly_price = price
        if data_price is None and (
            "Global External Application Load Balancer Inbound Data Processing" in desc
            or "Regional External Application Load Balancer Inbound Data Processing" in desc
        ):
            data_price = price
        if hourly_price is not None and data_price is not None:
            monthly = round(
                hourly_price * LB_ASSUMPTIONS["hours_per_month"] * LB_ASSUMPTIONS["load_balancers"]
                + data_price * LB_ASSUMPTIONS["data_transfer_gb"],
                2,
            )
            return {"unit_price": monthly, "unit": "LB workload", "monthly_price": monthly}
    if hourly_price is not None:
        monthly = round(hourly_price * LB_ASSUMPTIONS["hours_per_month"] * LB_ASSUMPTIONS["load_balancers"], 2)
        return {"unit_price": monthly, "unit": "LB workload", "monthly_price": monthly}
    return None


def _sku_gke_management(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """GKE cluster management fee (hourly)."""
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        if "Cluster Management" in desc or "management fee" in desc.lower():
            price = _sku_usd_price(sku)
            if price:
                return {"unit_price": price, "unit": "h"}
    return None


def _sku_cloud_run_requests(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """Cloud Run per-request pricing."""
    for sku in _list_skus(api_key, service_name):
        desc = sku.get("description", "")
        if "Request" in desc:
            price = _sku_usd_price(sku)
            if price:
                return {"unit_price": price, "unit": "requests"}
    return None


def _sku_first_match(api_key: str, service_name: str, region: str) -> Optional[Dict]:
    """Fallback: first USD-priced SKU in region."""
    for sku in _list_skus(api_key, service_name):
        regions = sku.get("serviceRegions", [])
        if region not in regions and "global" not in regions:
            continue
        price = _sku_usd_price(sku)
        if price:
            pi = sku.get("pricingInfo", [{}])[0]
            unit = pi.get("pricingExpression", {}).get("usageUnit", "unit")
            return {"unit_price": price, "unit": unit}
    return None


# ---------------------------------------------------------------------------
# Config table
# ---------------------------------------------------------------------------

GCP_SERVICE_CONFIG: Dict[str, Dict] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "compute engine": {
        "catalog_display": "Compute Engine",
        "sku_selector": _sku_e2_medium,
        "monthly_qty": 730, "unit_label": "Hrs (e2-medium)",
    },
    "google compute engine": {
        "catalog_display": "Compute Engine",
        "sku_selector": _sku_e2_medium,
        "monthly_qty": 730, "unit_label": "Hrs (e2-medium)",
    },
    # ── Database ─────────────────────────────────────────────────────────────
    "cloud sql": {
        "catalog_id": "services/9662-B51E-5089",
        "catalog_display": "Cloud SQL",
        "sku_selector": _sku_cloud_sql_mysql_small,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    "cloud sql for mysql": {
        "catalog_id": "services/9662-B51E-5089",
        "catalog_display": "Cloud SQL",
        "sku_selector": _sku_cloud_sql_mysql_small,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    "cloud sql for postgresql": {
        "catalog_id": "services/9662-B51E-5089",
        "catalog_display": "Cloud SQL",
        "sku_selector": _sku_cloud_sql_mysql_small,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    # ── Storage ───────────────────────────────────────────────────────────────
    "cloud storage": {
        "catalog_id": "services/95FF-2EF5-5EA1",
        "catalog_display": "Cloud Storage",
        "sku_selector": _sku_cloud_storage_standard,
        "monthly_qty": 100, "unit_label": "GB",
    },
    "google cloud storage": {
        "catalog_id": "services/95FF-2EF5-5EA1",
        "catalog_display": "Cloud Storage",
        "sku_selector": _sku_cloud_storage_standard,
        "monthly_qty": 100, "unit_label": "GB",
    },
    # ── Serverless ────────────────────────────────────────────────────────────
    "cloud run": {
        "catalog_id": "services/152E-C115-5142",
        "catalog_display": "Cloud Run",
        "sku_selector": _sku_cloud_run_requests,
        "monthly_qty": 1000000, "unit_label": "1M requests",
    },
    "cloud run functions": {
        "catalog_id": "services/29E7-DA93-CA13",
        "catalog_display": "Cloud Run Functions",
        "sku_selector": _sku_first_match,
        "monthly_qty": 1000000, "unit_label": "1M invocations",
    },
    "cloud functions": {
        "catalog_id": "services/29E7-DA93-CA13",
        "catalog_display": "Cloud Run Functions",
        "sku_selector": _sku_first_match,
        "monthly_qty": 1000000, "unit_label": "1M invocations",
    },
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "google kubernetes engine": {
        "catalog_display": "Google Kubernetes Engine",
        "sku_selector": _sku_gke_management,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    "gke": {
        "catalog_display": "Google Kubernetes Engine",
        "sku_selector": _sku_gke_management,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    # ── Load Balancing ────────────────────────────────────────────────────────
    # Native GCP LB pricing lives under the "Networking" service in the catalog
    "cloud load balancing": {
        "catalog_id": "services/E505-1604-58F8",
        "catalog_display": "Networking",
        "sku_selector": _sku_networking_lb_forwarding_rule,
        "monthly_qty": 1, "unit_label": "1 LB + 50 req/s + 100 GB + 730 hrs",
    },
    "cloud load balancer": {
        "catalog_id": "services/E505-1604-58F8",
        "catalog_display": "Networking",
        "sku_selector": _sku_networking_lb_forwarding_rule,
        "monthly_qty": 1, "unit_label": "1 LB + 50 req/s + 100 GB + 730 hrs",
    },
    # ── BigQuery ──────────────────────────────────────────────────────────────
    "bigquery": {
        "catalog_id": "services/24E6-581D-38E5",
        "catalog_display": "BigQuery",
        "sku_selector": _sku_first_match,
        "monthly_qty": 1, "unit_label": "TB",
    },
    # ── Pub/Sub ───────────────────────────────────────────────────────────────
    "cloud pub/sub": {
        "catalog_display": "Cloud Pub/Sub",
        "sku_selector": _sku_first_match,
        "monthly_qty": 1000000, "unit_label": "1M messages",
    },
    "google cloud pub/sub": {
        "catalog_display": "Cloud Pub/Sub",
        "sku_selector": _sku_first_match,
        "monthly_qty": 1000000, "unit_label": "1M messages",
    },
    # ── Memorystore (Redis / Valkey) ──────────────────────────────────────────
    "memorystore": {
        "catalog_id": "services/5AF5-2C11-D467",
        "catalog_display": "Cloud Memorystore for Redis",
        "sku_selector": _sku_first_match,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    "cloud memorystore": {
        "catalog_id": "services/5AF5-2C11-D467",
        "catalog_display": "Cloud Memorystore for Redis",
        "sku_selector": _sku_first_match,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
    "cloud memorystore for redis": {
        "catalog_id": "services/5AF5-2C11-D467",
        "catalog_display": "Cloud Memorystore for Redis",
        "sku_selector": _sku_first_match,
        "monthly_qty": 730, "unit_label": "Hrs",
    },
}

# Fallback aliases
GCP_ALIAS_TO_CONFIG_KEY: Dict[str, str] = {
    # ── Compute ──────────────────────────────────────────────────────────────
    "compute":                   "compute engine",
    "vm":                        "compute engine",
    "virtual machine":           "compute engine",
    "server":                    "compute engine",
    "web server":                "compute engine",
    "webserver":                 "compute engine",
    "app server":                "compute engine",
    "appserver":                 "compute engine",
    "container":                 "compute engine",
    "docker":                    "compute engine",
    # ── Database ─────────────────────────────────────────────────────────────
    "database":                  "cloud sql",
    "sql":                       "cloud sql",
    "mysql":                     "cloud sql for mysql",
    "postgres":                  "cloud sql for postgresql",
    "postgresql":                "cloud sql for postgresql",
    # ── Storage ───────────────────────────────────────────────────────────────
    "storage":                   "cloud storage",
    "object storage":            "cloud storage",
    "blob":                      "cloud storage",
    "gcs":                       "cloud storage",
    # ── Serverless / Functions ────────────────────────────────────────────────
    "functions":                 "cloud run functions",
    "function":                  "cloud run functions",
    "serverless":                "cloud run",
    "lambda":                    "cloud run functions",
    # ── Cache / Memorystore ───────────────────────────────────────────────────
    "cache":                     "memorystore",
    "redis":                     "memorystore",
    "memorystore for redis":     "memorystore",
    "google cloud memorystore":  "memorystore",
    "cloud memorystore for redis": "memorystore",
    # ── CDN ──────────────────────────────────────────────────────────────────
    "cdn":                       "cloud load balancing",
    "cloud cdn":                 "cloud load balancing",
    "google cloud cdn":          "cloud load balancing",
    # ── Load Balancing ────────────────────────────────────────────────────────
    "load balancer":             "cloud load balancing",
    "loadbalancer":              "cloud load balancing",
    "alb":                       "cloud load balancing",
    "nlb":                       "cloud load balancing",
    "application load balancer": "cloud load balancing",
    "network load balancer":     "cloud load balancing",
    # ── Kubernetes ────────────────────────────────────────────────────────────
    "kubernetes":                "google kubernetes engine",
    "k8s":                       "google kubernetes engine",
    "gke":                       "google kubernetes engine",
    # ── Messaging / Queue ─────────────────────────────────────────────────────
    "queue":                     "cloud pub/sub",
    "message queue":             "cloud pub/sub",
    "messaging":                 "cloud pub/sub",
    "pubsub":                    "cloud pub/sub",
    "pub/sub":                   "cloud pub/sub",
    # ── API Gateway ───────────────────────────────────────────────────────────
    "api gateway":               "cloud run",
    "apigateway":                "cloud run",
    "gateway":                   "cloud run",
    # ── NoSQL ────────────────────────────────────────────────────────────────
    "nosql":                     "cloud sql",
    "datastore":                 "bigquery",
    "firestore":                 "cloud sql",
}


# ---------------------------------------------------------------------------
# Catalog service lookup (cached per fetch_gcp_prices call)
# ---------------------------------------------------------------------------

def _list_catalog_services(api_key: str) -> Dict[str, str]:
    """Returns {display_name_lower: service_resource_name}."""
    result: Dict[str, str] = {}
    page_token = None
    while True:
        params = {"key": api_key}
        if page_token:
            params["pageToken"] = page_token
        r = httpx.get(f"{CATALOG_BASE_URL}/services", params=params, timeout=25.0)
        r.raise_for_status()
        data = r.json()
        for s in data.get("services", []):
            result[s.get("displayName", "").lower()] = s["name"]
        page_token = data.get("nextPageToken")
        if not page_token:
            return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_gcp_prices(
    api_key: str,
    components: List[Dict],
    region: str = "us-central1",
    project_id: Optional[str] = None,
) -> Optional[Dict]:
    """Fetch GCP pricing from the public Cloud Billing Catalog API using LLM equivalents."""
    if not api_key:
        logger.error("GCP API key is required")
        return None

    try:
        catalog = _list_catalog_services(api_key)
    except Exception as e:
        logger.error(f"Failed to list GCP catalog services: {e}")
        return None

    breakdown: List[Dict] = []
    total_monthly = 0.0

    for component in components:
        config_key = _resolve_config_key(component)
        if not config_key:
            logger.debug(f"No GCP config for component: {component.get('name')}")
            continue

        cfg = GCP_SERVICE_CONFIG[config_key]
        component_display = component.get("name") or config_key

        # Resolve the billing catalog service resource name
        if "catalog_id" in cfg:
            service_resource = cfg["catalog_id"]
        else:
            service_resource = catalog.get(cfg["catalog_display"].lower())
            if not service_resource:
                logger.warning(f"GCP: catalog service not found for '{cfg['catalog_display']}'")
                continue

        try:
            price = cfg["sku_selector"](api_key, service_resource, region)
        except Exception as e:
            logger.warning(f"GCP: SKU lookup failed for {config_key}: {e}")
            continue

        if not price:
            logger.warning(f"GCP: no SKU price for {config_key!r} in {region}")
            continue

        unit_price = price["unit_price"]
        if "monthly_price" in price:
            qty = 1
            monthly_cost = price["monthly_price"]
        else:
            qty = cfg["monthly_qty"]
            monthly_cost = round(unit_price * qty, 2)

        if monthly_cost > 0:
            breakdown.append({
                "service": cfg["catalog_display"],
                "component": component_display,
                "monthly_cost": monthly_cost,
                "unit": cfg["unit_label"],
                "quantity": qty,
                "unit_price": round(unit_price, 9),
            })
            total_monthly += monthly_cost
            logger.info(f"GCP {cfg['catalog_display']}: ${monthly_cost:.2f}/month")

    return {
        "monthly_estimate": round(total_monthly, 2),
        "annual_estimate": round(total_monthly * 12, 2),
        "currency": "USD",
        "region": region,
        "breakdown": breakdown,
        "assumptions": [
            "Prices from Google Cloud Billing Catalog API (public, API-key auth)",
            f"Region: {region}",
            "Standard tier SKUs — e2-medium compute, Cloud SQL small, standard storage",
            "730 hrs/month for hourly resources; 100 GB for storage",
            "Load Balancer workload: 1 LB, 50 requests/sec, 100 GB/month data processed, 730 hours/month",
        ],
    }


def _resolve_config_key(component: Dict) -> Optional[str]:
    candidates = [
        component.get("gcp_equivalent", ""),
        component.get("name", ""),
        component.get("category", ""),
        component.get("type", ""),
    ]
    for candidate in candidates:
        key = str(candidate or "").strip().lower()
        if key in GCP_SERVICE_CONFIG:
            return key
        if key in GCP_ALIAS_TO_CONFIG_KEY:
            return GCP_ALIAS_TO_CONFIG_KEY[key]
    return None
