import asyncio
from functools import partial
from fastapi import APIRouter, HTTPException
from typing import List
from app.models.schemas import WAFRequest, WAFReviewResponse
from app.services.waf_service import run_waf_review

router = APIRouter()


@router.post("/waf-review", response_model=List[WAFReviewResponse])
async def waf_review(request: WAFRequest):
    """
    Run Well-Architected Framework review across specified cloud providers.
    Returns scored pillar assessments with findings and recommendations.
    """
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            partial(run_waf_review, request.analysis, request.clouds, request.user_context),
        )
        return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"WAF review failed: {str(e)}")
