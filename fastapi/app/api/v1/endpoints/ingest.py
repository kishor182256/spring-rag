from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.schemas.ingest import ChunkResponse, FileChunksResponse, FileStatusResponse, UploadResult
from app.schemas.response import ApiResponse
from app.services.file_service import FileService
from app.services.processing_service import ProcessingStatus, processing_service

router = APIRouter(prefix="/ingest", tags=["Ingestion"])
file_service = FileService()


@router.post("/upload", response_model=ApiResponse[UploadResult])
async def upload_file(
    file: UploadFile = File(...),
    file_id: str | None = Form(default=None),
) -> ApiResponse[UploadResult]:
    if file.size == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    generated_file_id = file_id or str(uuid4())

    try:
        file_name, stored_path, size_in_bytes = await file_service.save(file)
    except ValueError as ex:
        raise HTTPException(status_code=400, detail=str(ex)) from ex

    processing_service.set_uploaded(generated_file_id, stored_path)

    return ApiResponse(
        success=True,
        message="File uploaded successfully",
        data=UploadResult(
            file_id=generated_file_id,
            status=ProcessingStatus.UPLOADED.value,
            file_name=file_name,
            stored_path=stored_path,
            size_in_bytes=size_in_bytes,
        ),
    )


@router.post("/{file_id}/process", response_model=ApiResponse[FileStatusResponse])
async def trigger_processing(file_id: str) -> ApiResponse[FileStatusResponse]:
    if processing_service.get_status(file_id) is None:
        raise HTTPException(status_code=404, detail="File id not found")

    processing_service.start_pipeline(file_id)

    status = processing_service.get_status(file_id)
    return ApiResponse(
        success=True,
        message="Processing started",
        data=FileStatusResponse(file_id=file_id, status=status.value),
    )


@router.get("/{file_id}/status", response_model=ApiResponse[FileStatusResponse])
async def get_processing_status(file_id: str) -> ApiResponse[FileStatusResponse]:
    status = processing_service.get_status(file_id)
    if status is None:
        raise HTTPException(status_code=404, detail="File id not found")

    message = "Status fetched"
    if status == ProcessingStatus.FAILED:
        failure_reason = processing_service.get_failure_reason(file_id)
        if failure_reason:
            message = f"Status fetched: {failure_reason}"

    return ApiResponse(
        success=True,
        message=message,
        data=FileStatusResponse(file_id=file_id, status=status.value),
    )


@router.get("/{file_id}/chunks", response_model=ApiResponse[FileChunksResponse])
async def get_chunks(
    file_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    include_text: bool = Query(default=False),
) -> ApiResponse[FileChunksResponse]:
    status = processing_service.get_status(file_id)
    if status is None:
        raise HTTPException(status_code=404, detail="File id not found")

    all_chunks = processing_service.get_chunks(file_id) or []
    paged_chunks = all_chunks[offset: offset + limit]
    chunk_payload = [
        ChunkResponse(
            chunk_id=chunk.chunk_id,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text if include_text else chunk.text[:120],
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
        )
        for chunk in paged_chunks
    ]

    return ApiResponse(
        success=True,
        message="Chunks fetched",
        data=FileChunksResponse(file_id=file_id, total_chunks=len(all_chunks), chunks=chunk_payload),
    )
