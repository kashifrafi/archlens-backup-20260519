from fastapi import APIRouter, HTTPException
from app.models.schemas import GithubPushRequest, GithubPushResponse
from app.services.github_service import push_to_github, GithubError

router = APIRouter()


@router.post("/github/push", response_model=GithubPushResponse)
async def github_push(request: GithubPushRequest):
    """
    Push the generated Terraform files to a GitHub repository.
    Creates the repo if missing (when create_if_missing=True). Token is used
    only for the duration of the request and is never logged or persisted.
    """
    try:
        return push_to_github(request)
    except GithubError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub push failed: {str(e)}")
