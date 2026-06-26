# Offline / air-gapped deployment — Docling models + client-provided vLLM

Status: shipped 2026-06-26 (v0.6.x)

## Context

Two operational requirements landed from the client simultaneously:

1. **No internet at runtime.** The deployment environment is air-gapped.
   Anything the backend currently downloads on first run must be baked
   into the Docker image at build time. The most material offender is
   Docling: on the first `DocumentConverter.convert()` call it pulls
   layout, TableFormer, EasyOCR, picture-classifier, and code-enricher
   weights — roughly 1.6 GB total — from Hugging Face. With no internet,
   the convert step would fail on day one.

2. **Client-provided vLLM server.** The client will host the Qwen3-VL
   model behind their own OpenAI-compatible endpoint. We no longer need
   to run a local `vllm` container in production — the existing code path
   that already targets vLLM via `OPENAI_BASE_URL` / `VLM_OPENAI_URL`
   (`CHAT_PROVIDER=openai`) is the entire interface.

Constraints preserved:

- 4-section Ask schema (Company Name / Address / Shipping / Goods
  Description) is the project contract — unchanged.
- PDF → docling MD → Ask LLM (now Qwen3-VL) → JSON pipeline is
  unchanged at the code level. The drift is purely deployment-side.
- Dev / test path keeps a local `vllm` service so the team can iterate
  without coordinating with the client infra.

## What changed

### Image build (offline Docling)

A new build stage `docling-model-baker` was added to
`document-parser/Dockerfile` (and the matching root `Dockerfile`):

```dockerfile
FROM python:3.12-slim AS docling-model-baker
RUN apt-get update && apt-get install -y --no-install-recommends \
    git libgl1 libglib2.0-0 libxcb-cursor0 libxcb-shape0 \
    libxcb-xfixes0 libxcb-render0 libxcb-randr0 libxcb-image0 \
    libxcb-keysyms1 libxcb-icccm4 libxcb-sync1 libxcb-xkb1 \
    libxkbcommon-x11-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "docling[easyocr]>=2.80.0,<3.0.0"

RUN docling-tools models download \
        layout tableformer tableformerv2 \
        picture_classifier code_formula \
        easyocr rapidocr \
        -o /opt/docling/models
```

The runtime stages (`base`, `local`, `remote`) copy the baked artifacts
into `/opt/docling/models` and set:

```dockerfile
ENV DOCLING_ARTIFACTS_PATH=/opt/docling/models \
    HF_HOME=/opt/docling/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
```

**Why a targeted list, not `--all`.** `docling-tools models download
--all` also pulls GraniteDocling, SmolVlm, Granite Vision 3.3 / 4.1,
the MLX variants, and Nemotron-OCR — ~25 GB of in-process VLMs we never
use. The VLM-direct path goes through the remote Ollama/vLLM endpoint,
so baking these in would be dead weight. The targeted list above is the
minimum the standard PdfPipelineOptions needs.

`HF_HUB_OFFLINE=1` is belt-and-braces — it makes any stray HF client
fail loud instead of silently phoning home. The `TRANSFORMERS_OFFLINE=1`
flag covers the same gap on the transformers side.

The artifacts path is the **parent directory** containing model folders
(`ds4sd--docling-models/`, `EasyOcr/`, etc.), per the upstream gotcha
documented in
[docling-project/docling#2555](https://github.com/docling-project/docling/issues/2555).

### vLLM endpoint (client-provided)

No code change. The single-model setup (shipped 2026-06-19) already
spoke OpenAI shape to vLLM on `:8000`. The migration is:

```dotenv
# Before: local vllm container
OPENAI_BASE_URL=http://host.docker.internal:8000/v1
VLM_OPENAI_URL=http://host.docker.internal:8000/v1/chat/completions

# After: client-provided vllm
OPENAI_BASE_URL=http://vllm-client.internal:8000/v1
VLM_OPENAI_URL=http://vllm-client.internal:8000/v1/chat/completions
```

Both pipelines (`CHAT_PROVIDER=openai` for Ask, the
`vlm_openai_url` path for VLM) use the same model alias
`qwen3-vl:8b-instruct` — the client just needs to serve under that
name via `--served-model-name`.

### Compose (dev / test)

The `vllm` service stays in `docker-compose.dev.yml` for local
testing. The `document-parser` service defaults to:

```yaml
CHAT_PROVIDER: openai
OPENAI_BASE_URL: http://host.docker.internal:8000/v1
VLM_OPENAI_URL: http://host.docker.internal:8000/v1/chat/completions
DOCLING_ARTIFACTS_PATH: /opt/docling/models
```

For a deployment against the client vLLM, override `OPENAI_BASE_URL`
and `VLM_OPENAI_URL` via `.env` (or `docker-compose.override.yml`) and
drop the local `vllm` service from the compose file.

### Host-side prefetch helper

`scripts/fetch_docling_models.sh` and
`scripts/fetch_docling_models.ps1` run the same model download on the
host, useful when:

- The Docker build host is offline but a separate staging host has
  internet — prefetch, then `COPY` the directory into the image.
- You want to inspect the artifact list before baking.
- You want to bind-mount the artifacts as a volume rather than bake
  them (e.g. shared NAS in a cluster).

## What was NOT changed

- `document-parser/infra/local_converter.py` — Docling usage is
  unchanged. The library's auto-discovery falls through to
  `DOCLING_ARTIFACTS_PATH` automatically.
- `infra/settings.py` — no new settings. `DOCLING_ARTIFACTS_PATH` is an
  env var Docling itself reads; we don't need to plumb it through the
  Settings dataclass.
- 4-section Ask schema / deep-extract merge logic — the pipeline runs
  identically. Only the URL of the model server moved.

## Verification

```bash
# 1. Build the local image (needs internet at build time only):
docker build -f document-parser/Dockerfile \
    --target local -t docling-studio-backend:local .

# 2. Confirm models are baked in:
docker run --rm docling-studio-backend:local \
    ls -1 /opt/docling/models
# Expected: ds4sd--docling-models  EasyOcr  ...

# 3. Confirm Docling finds them:
docker run --rm docling-studio-backend:local \
    python -c "from docling.document_converter import DocumentConverter; \
    c = DocumentConverter(); print('converter built OK')"

# 4. Bring up the full dev stack (vllm + parser + frontend):
docker compose -f docker-compose.dev.yml up -d

# 5. Smoke-test the Ask + VLM paths:
curl -s http://localhost:8002/api/health
curl -s http://host.docker.internal:8000/v1/models
```

## Rollback

If the offline build breaks something on a specific host:

1. Temporarily disable `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`
   in the Dockerfile to fall back to network downloads.
2. Set `DOCLING_ARTIFACTS_PATH=` (empty) to let Docling use its
   default cache location.
3. File an issue with the build host's HF cache contents so we can
   re-bake.

For client-vLLM rollback: set `CHAT_PROVIDER=ollama` and
`OPENAI_BASE_URL=` in `.env`, bring back the local `vllm` and
Ollama containers.