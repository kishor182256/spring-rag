from fastapi import APIRouter

from app.schemas.chat import ChatQueryRequest, ChatQueryResponse
from app.schemas.response import ApiResponse
from app.services.rag_service import RagService

router = APIRouter(prefix="/chat", tags=["Chat"])
rag_service = RagService()


@router.post("/query", response_model=ApiResponse[ChatQueryResponse])
def query_chat(payload: ChatQueryRequest) -> ApiResponse[ChatQueryResponse]:
    answer, source_count = rag_service.answer(payload.query)
    return ApiResponse(
        success=True,
        message="Query processed",
        data=ChatQueryResponse(answer=answer, source_count=source_count),
    )
