# VLM Ollama Backend & Ask JSON Schema Implementation

**Date**: 2025-01-XX  
**Status**: Implemented  
**Related**: User request for Ollama VLM integration and Ask feature JSON schema

## Summary

Implemented two major features:

1. **Ollama VLM Backend**: Added `qwen3-vl:8b` (Ollama-hosted) as a selectable VLM backend alongside the existing in-process Granite model
2. **Ask JSON Schema**: Rewrote the Ask feature prompt to extract trade/shipping document data as structured JSON (`section`, `field`, `value`)

## Changes

### Backend (document-parser)

#### Settings (`infra/settings.py`)
- Added `vlm_backend: str = "ollama"` - Backend selection ("ollama" or "granite")
- Added `vlm_ollama_model: str = "qwen3-vl:8b"` - Ollama model name
- Added `vlm_ollama_prompt: str` - Conversion prompt for Ollama VLM
- Added `vlm_remote_timeout: int = 300` - Timeout for remote VLM API calls
- Added validation for `vlm_backend` and `vlm_remote_timeout`

#### Converter (`infra/local_converter.py`)
- Split `_build_vlm_converter()` into three functions:
  - `_build_granite_vlm_converter()` - In-process transformers (existing logic)
  - `_build_ollama_vlm_converter()` - Remote Ollama API using `ApiVlmOptions` with `ResponseFormat.MARKDOWN`
  - `_build_vlm_converter()` - Router function that selects backend based on settings/options
- Added import for `ApiVlmOptions` and `ResponseFormat` from `docling.datamodel.pipeline_options_vlm_model`
- Per-analysis `vlm_backend` override supported via `ConversionOptions`

#### Domain (`domain/value_objects.py`)
- Added `vlm_backend: str = ""` to `ConversionOptions` dataclass

#### API Schemas (`api/schemas.py`)
- Added `vlm_backend` field to `PipelineOptions` Pydantic schema with camelCase alias
- Added validator for `vlm_backend` (must be "ollama", "granite", or empty)

#### Ask Feature (`api/chat.py`)
- Rewrote `_SYSTEM_PROMPT` to extract structured data as JSON array
- New schema: `[{"section": "...", "field": "...", "value": "..."}]`
- Included few-shot examples for trade/shipping documents (Company, Shipping Route, Goods, Financial, Dates)
- Preserved flexibility for Q&A while emphasizing JSON output for structured data

### Frontend

#### Types (`src/shared/types.ts`)
- Added `vlm_backend?: string` to `PipelineOptions` interface

#### i18n (`src/shared/i18n.ts`)
- Added French translations:
  - `config.vlmBackend`: "Moteur VLM"
  - `config.vlmBackendHint`: "Sélectionne le moteur VLM : Granite (local, transformers) ou Qwen3-VL (Ollama, distant)."
  - `config.vlmBackendGranite`: "Granite (local)"
  - `config.vlmBackendOllama`: "Qwen3-VL (Ollama)"
- Added English translations with same keys

#### UI (`src/features/analysis/ui/PipelineConfigDialog.vue`)
- Added VLM backend selector dropdown in VLM pipeline options section
- Options: "" (Granite - local) or "ollama" (Qwen3-VL - Ollama)
- Added `vlm_backend: ''` to `DEFAULT_OPTIONS`

### Configuration

#### Environment (`.env.example`)
- Documented all new VLM backend settings:
  - `VLM_BACKEND` (default: ollama)
  - `VLM_OLLAMA_MODEL` (default: qwen3-vl:8b)
  - `VLM_OLLAMA_PROMPT`
  - `VLM_REMOTE_TIMEOUT` (default: 300)
- Clarified `VLM_FALLBACK_MODEL` is granite-backend only

#### Docker Compose (`docker-compose.yml`, `docker-compose.dev.yml`)
- Added environment variables to `document-parser` service:
  - `VLM_BACKEND: ${VLM_BACKEND:-ollama}`
  - `VLM_FALLBACK_MODEL: ${VLM_FALLBACK_MODEL:-GRANITEDOCLING_TRANSFORMERS}`
  - `VLM_OLLAMA_MODEL: ${VLM_OLLAMA_MODEL:-qwen3-vl:8b}`
  - `VLM_OLLAMA_PROMPT: ${VLM_OLLAMA_PROMPT:-...}`
  - `VLM_REMOTE_TIMEOUT: ${VLM_REMOTE_TIMEOUT:-300}`

### Documentation

#### DOX Updates
- Updated `AGENTS.md` User Preferences section with VLM backend and Ask feature behavior
- Updated `document-parser/infra/AGENTS.md` Local Contracts with VLM backend variants

## Technical Details

### Ollama VLM Integration

The Ollama backend uses Docling's `ApiVlmOptions` to call the OpenAI-compatible `/v1/chat/completions` endpoint:

```python
vlm_options = ApiVlmOptions(
    url=f"{settings.ollama_host.rstrip('/')}/v1/chat/completions",
    params={"model": settings.vlm_ollama_model},
    prompt=settings.vlm_ollama_prompt,
    timeout=settings.vlm_remote_timeout,
    scale=image_scale,
    response_format=ResponseFormat.MARKDOWN,
)
```

**Key differences from Granite backend**:
- **Output format**: Markdown-only (no DocTags), so per-element bounding boxes are unavailable
- **Fallback handling**: Existing synthetic page structure fallback handles missing bboxes gracefully
- **Network**: Requires Ollama reachable at `OLLAMA_HOST` (default: `http://host.docker.internal:11434`)

### Ask JSON Schema

The new system prompt enforces a flat JSON array structure matching the spreadsheet model:

```json
[
  {"section": "Company", "field": "Shipper", "value": "FLUID LIMITED"},
  {"section": "Shipping Route", "field": "Port of Loading", "value": "Port of Felixstowe"},
  {"section": "Goods", "field": "Description", "value": "DOORS AND WINDOWS ACCESSORY"}
]
```

**Sections**: Company, Shipping Route, Goods, Financial, Dates (extensible)

The frontend already auto-detects JSON in assistant messages and provides a download button.

## Testing

- **Syntax validation**: All Python files compile successfully
- **Type checking**: Frontend `npm run type-check` passes
- **Manual testing required**:
  - Verify Ollama VLM conversion with `qwen3-vl:8b`
  - Test VLM backend selector in UI
  - Validate Ask feature JSON extraction with trade/shipping documents

## Deployment Notes

1. **Ollama setup**: Ensure `qwen3-vl:8b` is pulled on the host machine:
   ```bash
   ollama pull qwen3-vl:8b
   ```

2. **Environment variables**: Set `VLM_BACKEND=ollama` (default) or override per deployment

3. **Backward compatibility**: Setting `VLM_BACKEND=granite` restores original in-process behavior

4. **No-bbox caveat**: Ollama VLM output lacks per-element bounding boxes. The converter falls back to a synthetic single-paragraph page structure (existing behavior).

## Future Enhancements

- Add unit tests for VLM backend selection logic
- Add integration tests for Ollama VLM conversion
- Consider adding more VLM backends (e.g., OpenAI GPT-4V, Anthropic Claude Vision)
- Extend Ask JSON schema for other document types (invoices, receipts, contracts)
