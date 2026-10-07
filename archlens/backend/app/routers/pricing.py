import asyncio
from functools import partial
from fastapi import APIRouter, HTTPException
from app.models.schemas import PricingRequest, PricingComparisonResponse
from app.services.pricing_service import estimate_pricing

router = APIRouter()


@router.post("/pricing", response_model=PricingComparisonResponse)
async def compare_pricing(request: PricingRequest):
    """
    Estimate and compare cloud costs across AWS, Azure, and GCP.
    Returns per-service cost breakdown and a recommendation for the most cost-effective provider.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(estimate_pricing, request.analysis, request.region_preferences, request.user_context),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pricing estimation failed: {str(e)}")
