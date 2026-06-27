# Offline / air-gapped deployment — Docling models + client-provided vLLM

Status: shipped 2026-06-26 (v0.6.x); expanded to full 5-container system 2026-06-27

## Scope

This is the **internal design doc** for the offline-deployment surface.
The **client-facing walkthrough** lives at
[`docs/user-guide/airgap-deployment-guide.md`](../user-guide/airgap-deployment-guide.md)
— bilingual (中英對照), junior-engineer friendly, with copy-pasteable
`docker save` / `docker load` commands. Read this doc for the *why* and
the trade-offs; read the user-guide for the *how*.

## Context

Two operational requirements landed from the client simultaneously:

1. **No internet at runtime.** The deployment environment is air-gapped.
   The full system is **5 containers** — backend (`document-parser`),
   frontend, embedding, Neo4j, OpenSearch — and three of them
   (`document-parser`, frontend, embedding) currently reach external
   services at startup. Everything they would have downloaded must be
   baked into the image at build time. The other two (Neo4j, OpenSearch)
   are official Docker images that get pulled once on the build host
   and shipped as-is. See the per-container bake matrix in
   §"Bake matrix" below.

   The biggest single offender is still Docling: on the first
   `DocumentConverter.convert()` call it pulls layout, TableFormer,
   EasyOCR, picture-classifier, and code-enricher weights — roughly
   1.6 GB total — from Hugging Face. With no internet, the convert step
   would fail on day one.

2. **Client-provided vLLM server.** The client hosts the Qwen3-VL
   model behind their own OpenAI-compatible endpoint. We no longer run
   a local `vllm` container in production — the existing code path
   that already targets vLLM via `OPENAI_BASE_URL` / `VLM_OPENAI_URL`
   (`CHAT_PROVIDER=openai`) is the entire interface. The vLLM container
   is **not** part of the image bundle; it lives on the client side and
   is reachable over the internal network.

Constraints preserved:

- 4-section Ask schema (Company Name / Address / Shipping / Goods
  Description) is the project contract — unchanged.
- PDF → docling MD → Ask LLM (now Qwen3-VL) → JSON pipeline is
  unchanged at the code level. The drift is purely deployment-side.
- Dev / test path keeps a local `vllm` service so the team can iterate
  without coordinating with the client infra.

## Bake matrix

| Container | Base | External dep that needs baking | Build-stage approach |
|---|---|---|---|
| `document-parser` | `python:3.12-slim` | Docling ML weights (~1.6 GB from HF), pip wheels | New `docling-model-baker` stage; runtime uses `HF_HUB_OFFLINE=1` |
| `frontend` | multi-stage `node:20` → `nginx:alpine` | npm packages at build time (~50 MB) | Multi-stage build already caches `node_modules` in the build image; runtime is pure nginx + static files, nothing to fetch |
| `embedding` | `python:3.12-slim` | sentence-transformers model (~80 MB from HF), pip wheels | Bake the `all-MiniLM-L6-v2` (or Granite-30M) weights into `/opt/embedding/models/`; runtime sets `HF_HUB_OFFLINE=1` |
| `neo4j` | `neo4j:5.15-community` (official) | — (no per-startup download) | Pull once on build host, ship as-is |
| `opensearch` | `opensearchproject/opensearch:2` (official) | — (no per-startup download) | Pull once on build host, ship as-is |

Neo4j and OpenSearch don't reach out at startup, but they still need to
be transferred as Docker images because the air-gap host has no access
to Docker Hub. They're the cheapest two in the bundle (~1.5 GB total).

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

### Frontend + embedding bake (lighter)

These two are mechanically simpler than the Docling bake:

- **`frontend`** already uses a multi-stage build (`node:20` build
  stage → `nginx:alpine` runtime stage). The npm install runs during
  the build stage and only the compiled `dist/` ends up in the final
  image. The runtime image has no outbound network calls — it just
  serves static files. **No additional changes were needed** beyond
  what was already shipped.
- **`embedding`** follows the same pattern as `document-parser`: a
  build stage prefetches the sentence-transformers model into
  `/opt/embedding/models/`, the runtime stage copies it in and sets
  `HF_HUB_OFFLINE=1`. Smaller than Docling (~80 MB vs ~1.6 GB) but the
  same shape.

For per-image `docker build` commands and the exact compose template
the air-gap host needs, see
[`docs/user-guide/airgap-deployment-guide.md`](../user-guide/airgap-deployment-guide.md)
§6 ("Build offline images") and §10.2 ("Compose").

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
# 1. Build the backend image (needs internet at build time only):
docker build -f document-parser/Dockerfile \
    --target local -t docling-studio-backend:local .

# 2. Confirm Docling models are baked in:
docker run --rm docling-studio-backend:local \
    ls -1 /opt/docling/models
# Expected: ds4sd--docling-models  EasyOcr  ...

# 3. Confirm Docling finds them:
docker run --rm docling-studio-backend:local \
    python -c "from docling.document_converter import DocumentConverter; \
    c = DocumentConverter(); print('converter built OK')"

# 4. Build the other 4 images / pull the 2 official ones
#    (frontend, embedding, neo4j, opensearch). See the user-guide §6.

# 5. Bring up the full dev stack (vllm + 5 app containers):
docker compose -f docker-compose.dev.yml up -d

# 6. Smoke-test the Ask + VLM paths:
curl -s http://localhost:8002/api/health
curl -s http://host.docker.internal:8000/v1/models
```

For the full air-gap bring-up walkthrough (build → save → transfer →
load → compose → verify), see
[`docs/user-guide/airgap-deployment-guide.md`](../user-guide/airgap-deployment-guide.md).

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

## What we learned

- **Docling is by far the heaviest bake** (~1.6 GB). Frontend npm and
  embedding sentence-transformers combined add < 200 MB. Neo4j +
  OpenSearch are official images with no per-startup download, but
  still need to be transferred (~1.5 GB combined) because the air-gap
  host has no Docker Hub access.
- **`docling-tools models download --all` would have added ~25 GB of
  dead weight** (GraniteDocling, SmolVlm, Granite Vision, MLX
  variants, Nemotron-OCR). We use the VLM-direct path through the
  remote Ollama/vLLM endpoint instead of the in-process VLMs, so
  baking them in would have been pure bloat. The targeted subset is
  the minimum the standard `PdfPipelineOptions` actually loads.
- **`DOCLING_ARTIFACTS_PATH` must point to the parent directory**, not
  a specific model subfolder — Docling auto-discovers all sibling
  model folders under the path. Pointing it at a single subfolder
  triggers "downloads disabled" errors. See the upstream issue
  [docling-project/docling#2555](https://github.com/docling-project/docling/issues/2555).
- **`HF_HUB_OFFLINE=1` is belt-and-braces.** Even with the artifacts
  baked in, some transitive HF client might still try a metadata fetch.
  This flag makes those calls fail loud instead of silently phoning
  home — exactly what you want in a sealed environment.
- **The build host needs internet exactly once per image.** After the
  bundle is baked, neither the build host nor the air-gap host needs
  the network again. The air-gap host only talks to the client-hosted
  vLLM over the internal network.
- **Documenting for the full 5-container system, not just the
  backend.** The initial version of this doc and the user-guide focused
  on the `document-parser` image (where Docling lives). That was
  misleading — the air-gap deployment surface is all 5 containers. The
  user-guide was rewritten 2026-06-27 to be explicit about the per-
  container bake / pull / transfer matrix; this design doc was updated
  in lockstep to add the §"Bake matrix" table and the "Frontend +
  embedding bake" subsection.
- **Monkey-patching HTTP libraries is not a debug signal.** The
  earlier "Deep Extract silently fails on vLLM" symptom turned out to
  be the patch never being called (it patched `requests.post` but
  Docling uses `Session.send`). Fixed 2026-06-26 by also patching
  `Session.send` and routing content through a `_process_vlm_response`
  helper. Worth remembering for any other HTTP-interception work —
  patch the lowest level you can find.