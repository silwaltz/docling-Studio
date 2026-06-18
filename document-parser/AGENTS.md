# Backend Service (document-parser)

## Purpose

FastAPI backend providing document management, Docling-based analysis orchestration, chunking, ingestion, and chat capabilities. Implements hexagonal architecture with strict layer boundaries.

## Ownership

Backend team owns all Python code, API contracts, database schema, and service orchestration.

## Local Contracts

- **Architecture**: Hexagonal (ports & adapters). Dependencies flow inward: `api → services → domain`
- **Domain layer**: Pure Python, zero framework dependencies
- **API contract**: REST with camelCase JSON (Pydantic), snake_case internally
- **Database**: SQLite via aiosqlite, schema in `persistence/database.py`
- **Conversion modes**: `local` (in-process Docling) or `remote` (Docling Serve HTTP)
- **Extraction modes** (`extract_mode` on `PipelineOptionsRequest`):
  - `"standard"` (default) — single pipeline (standard or VLM-direct per `force_vlm_pipeline`).
  - `"deep"` — runs standard + Ask-LLM + VLM-direct-JSON, unions the two `content_json` outputs. See `domain/services.merge_extractions`. The standard's markdown/html remains the analysis surface.
- **Chat/extract quirks**: Gemma 4 (the Ask model) drops the wrapping `{ }` ~50% of the time, uses `key<1>` angle brackets, and uses `=` as separator. `api/chat.parse_ask_response` handles all three. Use it in any code path that parses Ask output.
- **Stuck-job recovery**: a container restart (or `asyncio.wait_for` timeout on `asyncio.to_thread`) clears the in-memory `asyncio.Task` but leaves the DB row at RUNNING. On startup, `main.py`'s `lifespan` calls `analysis_repo.fail_stale_running(older_than_seconds=2*conversion_timeout+300)` to flip stale RUNNING rows to FAILED. `AnalysisResponse.is_stale` lets the UI flag stuck jobs before the next sweep runs.
- **VLM runaway defense** (Ollama only, 2026-06-18): qwen3-vl-8b-instruct has been observed to enumerate fields without ever emitting `}` on dense multi-page content (doc1's pages 6-10 produced 17k-42k+ tokens without EOS). Two layers — `vlm_ollama_max_output_tokens` (default 4096, hard cap on output), and `_truncate_runaway_response` in the VLM HTTP patch (default `vlm_ollama_response_char_cap=32000`, defensive truncation at last balanced `}`). `vlm_ollama_stop_sequences` defaults to empty because Ollama's stop-token matcher is not JSON-string-aware (an earlier attempt to use `("}",)` truncated every valid JSON output from qwen3-vl on doc1). See `infra/AGENTS.md` for the full contract and `tests/test_vlm_runaway.py` for the safety net.
- **Testing**: pytest with 416+ tests, all must pass before merge
- **DDD granularity**: One route ≈ one domain operation (see `docs/design/269-backend-ddd-audit.md`)

## Work Guidance

- **Linting**: `ruff check . --fix` before commit
- **Formatting**: `ruff format .` before commit
- **Type hints**: Required for all public functions
- **Tests**: Add tests for new functionality, maintain >80% coverage
- **Error handling**: Use domain exceptions, map to HTTP status in API layer
- **Async**: Use async/await for I/O operations (DB, HTTP, file system)
- **Logging**: Use structured logging with `logging.getLogger(__name__)`
- **Config**: All settings via `infra/settings.py` (env vars)

## Verification

```bash
cd document-parser
ruff check .
ruff format . --check
pytest tests/ -v
```

## Child DOX Index

- `api/` - HTTP layer (FastAPI routers, Pydantic schemas)
- `domain/` - Pure domain logic (models, ports, value objects)
- `services/` - Use case orchestration
- `persistence/` - SQLite repositories
- `infra/` - Infrastructure adapters (converters, chunker, settings)
- `tests/` - pytest test suite

## Cross-references

- Deep-Extract scoring: `extracted-json/deep_extract__SHIPPED_REPORT.md`
- Ask-prompt tuning: `experiments/prompt-runs/FINAL_REPORT.md`

