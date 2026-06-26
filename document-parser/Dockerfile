# syntax=docker/dockerfile:1
# =============================================================================
# Docling Studio — backend image (multi-target: remote / local)
#
# The `local` target runs Docling in-process. To avoid runtime downloads,
# Docling's required model artifacts (layout model, TableFormer, EasyOCR,
# …) are pre-fetched during the Docker BUILD and baked into the image at
# `/opt/docling/models`. The runtime then points Docling at them via the
# `DOCLING_ARTIFACTS_PATH` env var — Docling will never try to reach the
# internet at runtime. The download happens at build time on a host that
# DOES have internet; the resulting image works fully offline.
#
# Usage:
#   docker build --target remote -t docling-studio-backend:remote .
#   docker build --target local  -t docling-studio-backend:local  .
# =============================================================================

# --- Stage: Docling model pre-fetch (build-time only, has internet) ------
# Installs `docling-tools` (the CLI that ships model downloads) and pulls
# every artifact Docling expects under DOCLING_ARTIFACTS_PATH. Build host
# needs internet for this single stage; the final image does NOT.
# --all covers: layout model, TableFormer, EasyOCR models, picture
# classifier, code/formula enrichers — basically every artifact Docling
# loads on first convert.
FROM python:3.12-slim AS docling-model-baker

# libxcb / libgl1 / libglib2 are needed by EasyOCR's OpenCV import at
# model-discovery time (the easyocr module's `model_downloader.py`
# imports cv2, which dlopens libxcb). libgl1 / libglib2 also cover the
# runtime needs of the layout + TableFormer stages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libgl1 \
    libglib2.0-0 \
    libxcb-cursor0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxcb-render0 \
    libxcb-randr0 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-icccm4 \
    libxcb-sync1 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    && rm -rf /var/lib/apt/lists/*

# Install docling + the CLI extras. The `docling-tools` CLI command is
# a console-script entry point declared in docling-slim's `cli` extra
# (pulled in via `standard`), NOT a separate PyPI package. The `easyocr`
# extra pulls EasyOCR weights/decoder code that the runtime converter
# uses via EasyOcrOptions. The downloader needs `models-local` to
# resolve the layout / TableFormer / picture-classifier model list.
RUN pip install --no-cache-dir \
    "docling[easyocr]>=2.80.0,<3.0.0"

# Bake models. `--all` fetches layout + TableFormer + EasyOCR + the
# picture-classifier and code-enricher weights. The `-o` path becomes the
# *parent directory* Docling expects under DOCLING_ARTIFACTS_PATH — subdirs
# like `ds4sd--docling-models/`, `EasyOcr/`, etc. land inside it.
# Pin HF cache to a known path so re-builds are idempotent and so the
# runtime can short-circuit any HF lookup with HF_HOME.
ENV HF_HOME=/opt/docling/.cache/huggingface \
    HF_HUB_CACHE=/opt/docling/.cache/huggingface/hub \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models

RUN mkdir -p /opt/docling/models \
    # Targeted download — `--all` would also pull GraniteDocling, SmolVlm,
    # Granite Vision, Granite Vision 4.1, MLX variants and Nemotron-OCR
    # (~25 GB total) that the runtime does NOT use. The standard pipeline
    # (PdfPipelineOptions) only needs layout + TableFormer; EasyOcrOptions
    # needs EasyOCR. VLM-direct path uses the remote Ollama/vLLM endpoint,
    # so the in-process VLMs are dead weight. Drop `--all` to keep the
    # image lean; add specific VLM ids (e.g. `granitedocling`) here if you
    # switch the runtime to vlm_backend=granite.
    && docling-tools models download \
        layout \
        tableformer \
        tableformerv2 \
        picture_classifier \
        code_formula \
        easyocr \
        rapidocr \
        -o /opt/docling/models \
    && echo "[docling-bake] Model artifacts at /opt/docling/models:" \
    && ls -1 /opt/docling/models


# --- Base: common deps for both targets ---
FROM python:3.12-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bake the model artifacts (built above) into the runtime image and hand
# them to the runtime user. `/opt/docling/models` must be the *parent
# directory* (not a single model folder) — see the comment in the
# `docling-model-baker` stage.
COPY --from=docling-model-baker /opt/docling/models /opt/docling/models
COPY --from=docling-model-baker /opt/docling/.cache /opt/docling/.cache

RUN useradd --create-home --shell /bin/bash appuser \
    && mkdir -p /app/uploads /app/data \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /opt/docling

EXPOSE 8000

ENV UPLOAD_DIR=/app/uploads \
    DB_PATH=/app/data/docling_studio.db \
    # Docling model discovery — points the library at the baked-in
    # artifacts dir; never falls back to the network.
    DOCLING_ARTIFACTS_PATH=/opt/docling/models \
    # HF cache so any ancillary HF loaders (e.g. tokenizer config) find
    # the same artifacts already on disk. No outbound traffic from here.
    HF_HOME=/opt/docling/.cache/huggingface \
    HF_HUB_CACHE=/opt/docling/.cache/huggingface/hub \
    # Belt-and-braces: stop Hugging Face from phoning home for updates.
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# --- Remote: lightweight, delegates to Docling Serve ---
# The remote target still gets the baked-in models (harmless — it never
# loads them) so a single image works for both topologies. If you need to
# shave bytes, build with `--target remote` and the model layer is reused
# from the cache; switching to a `--build-arg SKIP_BAKED_MODELS=1` arg
# is a future optimization.
FROM base AS remote
ENV CONVERSION_ENGINE=remote

# --- Local: full Docling in-process ---
FROM base AS local

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-local.txt .
# PyTorch nightly with CUDA 12.8 — required for Blackwell (RTX 50xx) GPUs.
# Stable PyTorch only supports up to CUDA 12.4; nightly adds sm_100 support.
ARG PYTORCH_INDEX=https://download.pytorch.org/whl/nightly/cu128
RUN pip install --no-cache-dir --pre torch torchvision --index-url ${PYTORCH_INDEX} \
    && pip install --no-cache-dir -r requirements-local.txt

RUN chown -R appuser:appuser /app \
    && chown -R appuser:appuser /usr/local/lib/python3.12/site-packages/rapidocr/models
USER appuser
ENV CONVERSION_ENGINE=local