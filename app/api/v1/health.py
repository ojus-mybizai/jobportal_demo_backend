from fastapi import APIRouter

from app.core.response import APIResponse, success_response


router = APIRouter(tags=["health"])


@router.get("/health", response_model=APIResponse[dict[str, str]])
async def health() -> APIResponse[dict[str, str]]:
    return success_response({"status": "ok"})
