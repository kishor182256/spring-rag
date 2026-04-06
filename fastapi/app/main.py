from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.services.file_service import FileService

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.on_event("startup")
def startup_event() -> None:
    FileService().ensure_upload_dir()
