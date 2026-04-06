# API Gateway

Single entry point for frontend clients.

## Run
```bash
cd "C:\gen ai project\api-gateway"
mvn spring-boot:run
```

## Port
- 8090

## Routed APIs
- `/api/v1/files/**` -> `lb://SPRINGBOOT-SERVICE` (via Eureka)
- `/api/v1/health` -> `lb://SPRINGBOOT-SERVICE`
- `/api/v1/chat/**` -> `http://localhost:8000`
- `/api/v1/ingest/**` -> `http://localhost:8000`

## Usage
Frontend can call only `http://localhost:8090`.
