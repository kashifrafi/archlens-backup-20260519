from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from app.services.validation_service import validate_terraform

router = APIRouter()


class ValidationRequest(BaseModel):
    files: List[Dict[str, Any]]  # list of {filename, content, description}


class FixRequest(BaseModel):
    files: List[Dict[str, Any]]
    cloud: str
    findings: List[str]


class RunRequest(BaseModel):
    files: List[Dict[str, Any]]
    cloud: str = "aws"
    run_plan: bool = True
    env_vars: Optional[Dict[str, str]] = None  # user-supplied cloud credentials


@router.post("/terraform/validate")
async def validate_terraform_code(request: ValidationRequest):
    """
    Run terraform fmt, tflint, checkov and terraform validate
    against the provided Terraform files and return a structured report.
    """
    try:
        result = validate_terraform(request.files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/terraform/run")
async def run_terraform_stream(request: RunRequest):
    """
    Stream terraform init → fmt → validate (with AI fix loop) → plan.
    Returns Server-Sent Events. Each event is:
      event: stage | stage_done | log | validate_errors | files_updated | done | error
      data: JSON object
    """
    from app.services.terraform_runner import run_terraform_stream  # noqa: E402

    async def _generate():
        async for chunk in run_terraform_stream(
            request.files,
            cloud=request.cloud,
            run_plan=request.run_plan,
            env_vars=request.env_vars,
        ):
            yield chunk

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class HcpPlanRequest(BaseModel):
    files: List[Dict[str, Any]]


@router.post("/terraform/hcp-plan")
async def run_hcp_plan_only(request: HcpPlanRequest):
    try:
        from app.services.validation_service import run_hcp_plan
        result = run_hcp_plan(request.files)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HCP plan failed: {str(e)}")


@router.post("/terraform/fix")
async def fix_terraform_code(request: FixRequest):
    try:
        from app.services.terraform_service import fix_security_issues
        from app.models.schemas import TerraformFile, CloudProvider

        files = [TerraformFile(**f) for f in request.files]
        cloud = CloudProvider(request.cloud)
        fixed = fix_security_issues(files, cloud, request.findings)
        return {
            "files": [
                {"filename": f.filename, "content": f.content, "description": f.description}
                for f in fixed
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI fix failed: {str(e)}")
