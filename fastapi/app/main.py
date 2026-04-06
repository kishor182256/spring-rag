import json
import urllib.request

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.services.file_service import FileService

app = FastAPI(title=settings.app_name)
app.include_router(api_router)


@app.on_event("startup")
def startup_event() -> None:
    FileService().ensure_upload_dir()
    if settings.llm_provider.lower().strip() == "ollama":
        _warmup_ollama()


def _warmup_ollama() -> None:
    """
    Preload Ollama model to reduce first-query latency.
    Best effort only; failures are intentionally ignored.
    """
    try:
        base_url = settings.ollama_base_url.rstrip("/")
        payload = {
            "model": settings.ollama_chat_model,
            "stream": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {"num_predict": 8, "temperature": 0.0},
            "prompt": "Reply with one word: ready",
        }
        request = urllib.request.Request(
            url=base_url + "/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=12):
            pass
    except Exception:
        # Keep startup resilient even if Ollama is not ready yet.
        pass
