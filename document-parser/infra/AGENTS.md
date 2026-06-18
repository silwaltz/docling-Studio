# Infrastructure Layer (infra)

## Purpose

Infrastructure adapters implementing domain ports: converters (local/remote Docling), chunker, LLM clients, Neo4j, settings, rate limiter.

## Ownership

Backend team owns adapter implementations and external service integrations.

## Local Contracts

- **Adapters**: Implement protocols defined in `domain/ports.py`
- **Settings**: All config via `settings.py` (env vars with defaults)
- **External services**: Docling Serve, Ollama, Neo4j, OpenSearch
- **VLM backends**: Two VLM converter variants - `granite` (in-process transformers) and `ollama` (remote API via qwen3-vl:8b)
- **VLM output modes** (Ollama only, selected by `options.vlm_output_mode`): `json` (default, four canonical sections) or `markdown` (extract everything, preserve structure). Each mode has its own prompt (`vlm_ollama_prompt` / `vlm_ollama_markdown_prompt`) and its own per-page response bucket in the VLM HTTP patch.
- **VLM runaway defense** (Ollama, 2026-06-18): the qwen3-vl-8b-instruct model has been observed to enumerate fields without ever emitting `}` on dense multi-page content (doc1's pages 6-10 produced 17k-42k+ tokens without EOS — see `docling-studio/deep-extract-v3` memory). Two layers of defense; all wired through `Settings` and `_build_ollama_vlm_converter`:
  1. **`vlm_ollama_max_output_tokens`** (default 4096) — `max_tokens` param sent to Ollama. Primary defense: hard cap on output length.
  2. **`vlm_ollama_response_char_cap`** (default 32000) — defensive cap in the VLM HTTP patch (`_truncate_runaway_response`). Truncates a runaway response at the last balanced `}` or hard-truncates + appends `}`. Always returns a closed string the downstream parser can fail-fast on. Per-runaway warning + per-document summary log via `_get_vlm_runaway_stats()`.
  - Related (not new in this fix but rebalanced): `vlm_ollama_max_tokens` (default 16384) is `num_ctx` ONLY; `vlm_remote_timeout` (default 600s) bounds the per-call wall clock.
  - **`vlm_ollama_stop_sequences`** (default `()`) is intentionally empty. An earlier attempt to use `("}",)` truncated every valid JSON output from qwen3-vl because Ollama's stop-token matcher is not JSON-string-aware (it stops at the first `}` anywhere in the output, including inside string values). The field is still configurable for operators who want to experiment with non-JSON output modes.
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
