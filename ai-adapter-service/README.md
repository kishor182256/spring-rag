# AI Adapter Service

Spring Boot proxy service for FastAPI endpoints. Registers with Eureka.

## Run
```bash
cd "C:\gen ai project\ai-adapter-service"
mvn spring-boot:run
```

## Port
- 8081

## Proxied Endpoints
- POST `/api/v1/chat/query`
- POST `/api/v1/ingest/upload`
- POST `/api/v1/ingest/{fileId}/process`
- GET `/api/v1/ingest/{fileId}/status`
- GET `/api/v1/ingest/{fileId}/chunks`
- GET `/api/v1/health/fastapi`