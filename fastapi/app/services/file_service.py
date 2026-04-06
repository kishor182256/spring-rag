from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import UPLOAD_DIR_PATH


class FileService:
    def ensure_upload_dir(self) -> None:
        UPLOAD_DIR_PATH.mkdir(parents=True, exist_ok=True)

    async def save(self, file: UploadFile) -> tuple[str, str, int]:
        if not file.filename:
            raise ValueError("File name is missing")

        safe_name = Path(file.filename).name
        stored_name = f"{uuid4()}_{safe_name}"
        target_path = UPLOAD_DIR_PATH / stored_name

        content = await file.read()
        target_path.write_bytes(content)

        return safe_name, str(target_path.resolve()), len(content)
