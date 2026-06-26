# syntax=docker/dockerfile:1
# =============================================================================
# Docling Studio — single-image build (frontend + backend, multi-target)
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
#   docker build --target remote -t docling-studio:remote .
#   docker build --target local  -t docling-studio:local  .
# =============================================================================

# --- Stage 1: Build frontend assets ---
FROM node:20-alpine AS frontend-build

ARG APP_VERSION=dev

WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN VITE_APP_VERSION=${APP_VERSION} npm run build

# --- Stage 2: Pre-fetch Docling model artifacts (build-time, needs net) ---
# Pulls every artifact Docling expects under DOCLING_ARTIFACTS_PATH. The
# `local` target bakes these into the runtime image; the `remote` target
# ignores them (Docling Serve holds its own models in its own container).
# Both targets share this stage so the cache layer is reusable.
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

RUN pip install --no-cache-dir \
    "docling[easyocr]>=2.80.0,<3.0.0"

ENV HF_HOME=/opt/docling/.cache/huggingface \
    HF_HUB_CACHE=/opt/docling/.cache/huggingface/hub \
    DOCLING_ARTIFACTS_PATH=/opt/docling/models

RUN mkdir -p /opt/docling/models \
    # Targeted download — `--all` would also pull GraniteDocling, SmolVlm,
    # Granite Vision, Granite Vision 4.1, MLX variants and Nemotron-OCR
    # (~25 GB total) that the runtime does NOT use. The standard pipeline
    # only needs layout + TableFormer; EasyOcrOptions needs EasyOCR. VLM-
    # direct uses the remote Ollama/vLLM endpoint, so in-process VLMs are
    # dead weight. Drop `--all` to keep the image lean.
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


# --- Stage 3: Base runtime (Python + Nginx) ---
FROM python:3.12-slim AS base

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# System deps: poppler (pdf2image), nginx, gettext-base (envsubst for nginx template)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    nginx \
    gettext-base \
    && rm -rf /var/lib/apt/lists/*

# Python deps (common)
WORKDIR /app
COPY document-parser/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Backend code
COPY document-parser/ .

# Bake the model artifacts (built above) into the runtime image.
COPY --from=docling-model-baker /opt/docling/models /opt/docling/models
COPY --from=docling-model-baker /opt/docling/.cache /opt/docling/.cache

# Frontend static files
COPY --from=frontend-build /build/dist /usr/share/nginx/html

# Nginx config (template stored outside sites-enabled to avoid nginx loading it raw)
COPY nginx.conf.template /etc/nginx/default.template

# Non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Data directories + model dir ownership
RUN mkdir -p /app/uploads /app/data \
    && chown -R appuser:appuser /app \
    && chown -R appuser:appuser /opt/docling

ENV UPLOAD_DIR=/app/uploads \
    DB_PATH=/app/data/docling_studio.db \
    NGINX_MAX_BODY_SIZE=200M \
    # Docling model discovery — points the library at the baked-in
    # artifacts dir; never falls back to the network.
    DOCLING_ARTIFACTS_PATH=/opt/docling/models \
    HF_HOME=/opt/docling/.cache/huggingface \
    HF_HUB_CACHE=/opt/docling/.cache/huggingface/hub \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

EXPOSE 3000

CMD ["sh", "-c", "envsubst '${NGINX_MAX_BODY_SIZE}' < /etc/nginx/default.template > /etc/nginx/sites-enabled/default && nginx && exec su appuser -c 'uvicorn main:app --host 127.0.0.1 --port 8000'"]

# --- Remote: lightweight, delegates to Docling Serve ---
FROM base AS remote
ENV CONVERSION_ENGINE=remote

# --- Local: full Docling in-process ---
FROM base AS local

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY document-parser/requirements-local.txt .
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements-local.txt

RUN chown -R appuser:appuser /app \
    && chown -R appuser:appuser /usr/local/lib/python3.12/site-packages/rapidocr/models
ENV CONVERSION_ENGINE=local