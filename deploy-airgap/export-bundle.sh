#!/usr/bin/env bash
# =============================================================================
# Build the air-gap image bundle (SINGLE-MACHINE: vllm + backend + frontend)
# from this repo.
#
# Run on the BUILD HOST (online, one time). Produces:
#   deploy-airgap/bundle/vllm.tar.gz
#   deploy-airgap/bundle/backend.tar.gz
#   deploy-airgap/bundle/frontend.tar.gz
#   deploy-airgap/bundle/bundle.sha256
#
# Then transfer bundle/*.tar.gz + bundle/bundle.sha256 to the air-gap host.
# =============================================================================
set -euo pipefail

# Resolve script directory so the script works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="$SCRIPT_DIR/bundle"

mkdir -p "$BUNDLE_DIR"

cd "$REPO_ROOT"

echo "=== Building docling-studio-vllm:offline ==="
docker build \
    --platform linux/amd64 \
    -f deploy-airgap/Dockerfile.vllm \
    --build-arg VLLM_BASE=vllm/vllm-openai:latest \
    --build-arg VLLM_HF_MODEL=cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit \
    -t docling-studio-vllm:offline \
    deploy-airgap/

echo
echo "=== Building docling-studio-backend:offline ==="
docker build \
    --platform linux/amd64 \
    --target local \
    -t docling-studio-backend:offline \
    -f document-parser/Dockerfile \
    document-parser/

echo
echo "=== Building docling-studio-frontend:offline ==="
docker build \
    --platform linux/amd64 \
    -t docling-studio-frontend:offline \
    -f frontend/Dockerfile \
    frontend/

echo
echo "=== Verifying baked-in vLLM model weights ==="
docker run --rm docling-studio-vllm:offline \
    sh -c 'ls -la /root/.cache/huggingface/hub 2>/dev/null && \
            du -sh /root/.cache/huggingface/hub/* 2>/dev/null'

echo
echo "=== Verifying baked-in Docling models ==="
docker run --rm docling-studio-backend:offline ls -1 /opt/docling/models

echo
echo "=== Verifying baked-in EasyOCR + layout + TableFormer import works without network ==="
docker run --rm --network=none docling-studio-backend:offline \
    python -c "from docling.document_converter import DocumentConverter; \
    c = DocumentConverter(); print('converter built OK, no network needed')"

echo
echo "=== Verifying frontend static build ==="
docker run --rm docling-studio-frontend:offline \
    ls /usr/share/nginx/html | head -5

echo
echo "=== Exporting images ==="
cd "$BUNDLE_DIR"
docker save -o vllm.tar      docling-studio-vllm:offline
docker save -o backend.tar   docling-studio-backend:offline
docker save -o frontend.tar  docling-studio-frontend:offline
gzip -f vllm.tar backend.tar frontend.tar

echo
echo "=== Computing SHA-256 ==="
sha256sum vllm.tar.gz backend.tar.gz frontend.tar.gz > bundle.sha256
cat bundle.sha256

echo
echo "=== Bundle ready at: $BUNDLE_DIR ==="
ls -lh "$BUNDLE_DIR"
echo
echo "Next: transfer vllm.tar.gz, backend.tar.gz, frontend.tar.gz, bundle.sha256 to the air-gap host."
echo "On the air-gap host:"
echo "  sha256sum -c bundle.sha256"
echo "  gunzip -k *.tar.gz"
echo "  docker load -i vllm.tar"
echo "  docker load -i backend.tar"
echo "  docker load -i frontend.tar"
echo "  # then place docker-compose.yml + .env in /opt/docling-studio/ and"
echo "  # run 'docker compose up -d' — see deploy-airgap/README.md"
