from typing import Dict, Optional
import logging

from app.config import settings
from app.models.schemas import (
    DiagramAnalysisResponse,
    CloudProvider,
    PricingComparisonResponse,
    PricingEstimateResponse,
    PricingBreakdownItem,
    UserContext,
)
from app.services.aws_pricing import fetch_aws_prices
from app.services.azure_pricing import fetch_azure_prices
from app.services.gcp_pricing import fetch_gcp_prices

logger = logging.getLogger(__name__)


# Default regions for pricing lookup
DEFAULT_REGIONS = {
    CloudProvider.AWS: "us-east-1",
    CloudProvider.AZURE: "eastus",
    CloudProvider.GCP: "us-central1",
}


def estimate_pricing(
    analysis: DiagramAnalysisResponse,
    region_preferences: Optional[Dict[str, str]] = None,
    user_context: Optional[UserContext] = None,
) -> PricingComparisonResponse:
    """
    Estimate and compare pricing across all three cloud providers.
    Uses provider pricing APIs only; no LLM or local pricing fallback.
    """
    regions = {
        "aws": (region_preferences or {}).get("aws", DEFAULT_REGIONS[CloudProvider.AWS]),
        "azure": (region_preferences or {}).get("azure", DEFAULT_REGIONS[CloudProvider.AZURE]),
        "gcp": (region_preferences or {}).get("gcp", DEFAULT_REGIONS[CloudProvider.GCP]),
    }

    # Price every component individually — if the diagram has 2 EC2 instances,
    # both are priced separately. Each component's {cloud}_equivalent field
    # (set by the LLM during analysis) drives the lookup in each provider's
    # config table.
    components = [
        {
            "name": c.name,
            "category": c.category,
            "type": c.type,
            "aws_equivalent": c.aws_equivalent,
            "azure_equivalent": c.azure_equivalent,
            "gcp_equivalent": c.gcp_equivalent,
        }
        for c in analysis.components
    ]

    if not settings.aws_access_key_id or not settings.aws_secret_access_key:
        raise ValueError("AWS pricing requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY.")
    if not settings.gcp_api_key:
        raise ValueError("GCP pricing requires GCP_API_KEY for the public Cloud Billing Catalog API.")

    aws_estimate = _to_estimate(
        fetch_aws_prices(
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
            components=components,
            region=regions["aws"],
        ),
        CloudProvider.AWS,
        regions["aws"],
    )
    azure_estimate = _to_estimate(
        fetch_azure_prices(components=components, region=regions["azure"]),
        CloudProvider.AZURE,
        regions["azure"],
    )
    gcp_estimate = _to_estimate(
        fetch_gcp_prices(
            api_key=settings.gcp_api_key,
            components=components,
            region=regions["gcp"],
            project_id=settings.gcp_project_id,
        ),
        CloudProvider.GCP,
        regions["gcp"],
    )

    missing = [
        cloud
        for cloud, estimate in {
            "aws": aws_estimate,
            "azure": azure_estimate,
            "gcp": gcp_estimate,
        }.items()
        if not estimate or not estimate.breakdown
    ]
    if missing:
        raise ValueError(f"Pricing API did not return usable data for: {', '.join(missing)}")

    estimates = {
        "aws": aws_estimate.monthly_estimate,
        "azure": azure_estimate.monthly_estimate,
        "gcp": gcp_estimate.monthly_estimate,
    }
    cheapest = min(estimates, key=estimates.get)

    return PricingComparisonResponse(
        aws=aws_estimate,
        azure=azure_estimate,
        gcp=gcp_estimate,
        cheapest=cheapest,
        recommendation=f"{cheapest.upper()} has the lowest API-returned estimate for the mapped architecture components.",
    )


def _to_estimate(data: Optional[Dict], cloud: CloudProvider, default_region: str) -> Optional[PricingEstimateResponse]:
    if not data:
        return None
    breakdown = [PricingBreakdownItem(**item) for item in data.get("breakdown", [])]
    return PricingEstimateResponse(
        cloud=cloud,
        monthly_estimate=data.get("monthly_estimate", 0.0),
        annual_estimate=data.get("annual_estimate", 0.0),
        currency=data.get("currency", "USD"),
        region=data.get("region", default_region),
        breakdown=breakdown,
        assumptions=data.get("assumptions", []),
    )
