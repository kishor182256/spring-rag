from fastapi import APIRouter

from app.schemas.response import ApiResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=ApiResponse[dict])
def health_check() -> ApiResponse[dict]:
    return ApiResponse(success=True, message="FastAPI service is healthy", data={"status": "UP"})
