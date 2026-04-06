# FastAPI Service

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

## Endpoints

- `GET /api/v1/health`
- `POST /api/v1/ingest/upload` (form-data key: `file`, optional `file_id`)
- `POST /api/v1/ingest/{file_id}/process`
- `GET /api/v1/ingest/{file_id}/status`
- `GET /api/v1/ingest/{file_id}/chunks`
- `POST /api/v1/chat/query`

## Notes

- Uploaded files are stored under `storage/uploads`.
- Upload directory is created once during application startup.
- Chunking currently supports PDF files only.
- Chunking strategy is general-purpose sentence-window with overlap (not heading-dependent).
- Embedding MVP supports:
  - `EMBEDDING_PROVIDER=local` (default, no API key needed)
  - `EMBEDDING_PROVIDER=openai` (set `OPENAI_API_KEY`)
