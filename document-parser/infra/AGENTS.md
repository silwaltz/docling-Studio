# Infrastructure Layer (infra)

## Purpose

Infrastructure adapters implementing domain ports: converters (local/remote Docling), chunker, LLM clients, Neo4j, settings, rate limiter.

## Ownership

Backend team owns adapter implementations and external service integrations.

## Local Contracts

- **Adapters**: Implement protocols defined in `domain/ports.py`
- **Settings**: All config via `settings.py` (env vars with defaults)
- **External services**: Docling Serve, Ollama, Neo4j, OpenSearch
- **Error handling**: Catch external errors, translate to domain exceptions
- **Timeouts**: Configure timeouts for all external HTTP calls
- **Retries**: Implement retry logic for transient failures

## Work Guidance

- **New adapter**: Implement domain port protocol, add to this directory
- **Settings**: Add new env vars to `settings.py` with type hints and defaults
- **HTTP clients**: Use `httpx.AsyncClient` with timeout and retry config
- **Secrets**: Never log secrets, use environment variables
- **Testing**: Mock external services in tests
- **Health checks**: Implement health checks for external dependencies

## Verification

Infra tests in `tests/test_infra_*.py` mock external services

## Child DOX Index

- `llm/` - LLM client adapters (Ollama)
- `neo4j/` - Neo4j graph database adapter
- `secrets/` - Secret encryption/decryption utilities
