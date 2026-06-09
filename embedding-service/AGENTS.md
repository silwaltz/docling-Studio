# Embedding Service (embedding-service)

## Purpose

Standalone FastAPI microservice providing text embedding via sentence-transformers. Supports multiple models (all-MiniLM-L6-v2, Granite 30M).

## Ownership

Backend team owns service code and model integration. Ops team owns deployment and scaling.

## Local Contracts

- **Framework**: FastAPI with sentence-transformers
- **Models**: Configurable via `EMBEDDING_MODEL` env var
- **Batch processing**: Configurable via `EMBEDDING_BATCH_SIZE` env var
- **Health check**: `/health` endpoint for container orchestration
- **Resource limits**: 2GB memory limit in docker-compose
- **Startup time**: ~2 minutes for model download on first run

## Work Guidance

- **Model changes**: Update `EMBEDDING_MODEL` in `.env`, rebuild container
- **Performance**: Tune `EMBEDDING_BATCH_SIZE` based on memory/throughput tradeoff
- **Testing**: Use `test_main.py` for unit tests
- **Logging**: Use FastAPI logging, structured format
- **Error handling**: Return 5xx for model errors, 4xx for input validation

## Verification

```bash
cd embedding-service
pytest test_main.py -v
docker build -t embedding-service .
docker run -p 8001:8001 embedding-service
curl http://localhost:8001/health
```

## Child DOX Index

None (single-service, no subdirectories)
