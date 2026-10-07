import asyncio
from functools import partial
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.schemas import TerraformRequest, TerraformGenerateResponse
from app.services.terraform_service import generate_terraform, generate_terraform_stream

router = APIRouter()


@router.post("/terraform", response_model=TerraformGenerateResponse)
async def generate_terraform_code(request: TerraformRequest):
    """
    Generate production-ready Terraform IaC for the chosen cloud provider.
    Returns modular .tf files ready to apply.
    """
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            partial(
                generate_terraform,
                request.analysis,
                request.cloud,
                request.region,
                request.include_modules,
                request.user_context,
            ),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Terraform generation failed: {str(e)}")


@router.post("/terraform/stream")
async def generate_terraform_code_stream(request: TerraformRequest):
    """
    Streaming SSE version of /terraform.
    Yields progress events so the frontend can show real-time step status.
    """
    async def _gen():
        async for chunk in generate_terraform_stream(
            request.analysis,
            request.cloud,
            request.region,
            request.include_modules,
            request.user_context,
        ):
            yield chunk

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
