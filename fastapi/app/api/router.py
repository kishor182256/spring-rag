from fastapi import APIRouter

from app.api.v1.endpoints import chat, health, ingest
from app.core.config import settings

api_router = APIRouter(prefix=settings.api_v1_prefix)
api_router.include_router(health.router)
api_router.include_router(chat.router)
api_router.include_router(ingest.router)
