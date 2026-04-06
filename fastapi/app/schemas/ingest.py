from pydantic import BaseModel


class UploadResult(BaseModel):
    file_id: str
    status: str
    file_name: str
    stored_path: str
    size_in_bytes: int


class FileStatusResponse(BaseModel):
    file_id: str
    status: str


class ChunkResponse(BaseModel):
    chunk_id: str
    page_start: int
    page_end: int
    text: str
    start_offset: int
    end_offset: int


class FileChunksResponse(BaseModel):
    file_id: str
    total_chunks: int
    chunks: list[ChunkResponse]
