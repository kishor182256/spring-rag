from pydantic import BaseModel, Field


class ChatQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, description="User question")


class ChatQueryResponse(BaseModel):
    answer: str
    source_count: int
