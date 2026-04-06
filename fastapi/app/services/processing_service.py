import asyncio
from enum import StrEnum

from app.services.chunking_service import ChunkRecord, ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.text_extraction_service import TextExtractionService
from app.services.vector_store_service import vector_store


class ProcessingStatus(StrEnum):
    UPLOADED = "UPLOADED"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class ProcessingService:
    def __init__(self) -> None:
        self._status_by_file_id: dict[str, ProcessingStatus] = {}
        self._path_by_file_id: dict[str, str] = {}
        self._chunks_by_file_id: dict[str, list[ChunkRecord]] = {}
        self._failure_reason_by_file_id: dict[str, str] = {}
        self._text_extraction_service = TextExtractionService()
        self._chunking_service = ChunkingService()
        self._embedding_service = EmbeddingService()

    def set_uploaded(self, file_id: str, stored_path: str) -> None:
        self._status_by_file_id[file_id] = ProcessingStatus.UPLOADED
        self._path_by_file_id[file_id] = stored_path

    def get_status(self, file_id: str) -> ProcessingStatus | None:
        return self._status_by_file_id.get(file_id)

    def get_chunks(self, file_id: str) -> list[ChunkRecord] | None:
        return self._chunks_by_file_id.get(file_id)

    def get_failure_reason(self, file_id: str) -> str | None:
        return self._failure_reason_by_file_id.get(file_id)

    def start_pipeline(self, file_id: str) -> None:
        status = self.get_status(file_id)
        if status is None:
            raise ValueError("File id not found")
        if status in {ProcessingStatus.CHUNKING, ProcessingStatus.EMBEDDING, ProcessingStatus.INDEXED}:
            return

        self._status_by_file_id[file_id] = ProcessingStatus.CHUNKING
        asyncio.create_task(self._run_pipeline(file_id))

    async def _run_pipeline(self, file_id: str) -> None:
        try:
            stored_path = self._path_by_file_id.get(file_id)
            if not stored_path:
                raise ValueError("Stored file path not found for file id")

            pages = self._text_extraction_service.extract_pages(stored_path)
            chunks = self._chunking_service.split_pages(file_id=file_id, pages=pages)
            self._chunks_by_file_id[file_id] = chunks

            self._status_by_file_id[file_id] = ProcessingStatus.EMBEDDING
            texts = [chunk.text for chunk in chunks]
            vectors = await asyncio.to_thread(self._embedding_service.embed_texts, texts)
            vector_store.upsert_file_chunks(file_id=file_id, chunks=chunks, vectors=vectors)

            self._status_by_file_id[file_id] = ProcessingStatus.INDEXED
        except Exception as ex:
            self._status_by_file_id[file_id] = ProcessingStatus.FAILED
            self._failure_reason_by_file_id[file_id] = str(ex)


processing_service = ProcessingService()
