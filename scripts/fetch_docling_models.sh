#!/bin/bash
# =============================================================================
# Pre-fetch Docling model artifacts to a local directory.
#
# Runs the same download the `docling-model-baker` stage runs inside the
# Dockerfile, but on the host — useful when:
#   - The build host is offline but a separate staging host has internet.
#   - You want to inspect what artifacts Docling expects before baking.
#   - You want to bind-mount the artifacts as a volume rather than bake.
#
# Usage:
#   ./scripts/fetch_docling_models.sh [output-dir]
#     Default output-dir: ./docling-models
#
# Then either:
#   - bake into the image via the Dockerfile (default), OR
#   - mount into the running container:
#       volumes:
#         - ./docling-models:/opt/docling/models:ro
#       environment:
#         DOCLING_ARTIFACTS_PATH: /opt/docling/models
# =============================================================================
set -euo pipefail

OUT_DIR="${1:-$(dirname "$0")/../docling-models}"
OUT_DIR="$(cd "$(dirname "$OUT_DIR")" && pwd)/$(basename "$OUT_DIR")"

echo "==> Pre-fetching Docling model artifacts to: $OUT_DIR"
mkdir -p "$OUT_DIR"

# Use a dedicated venv so we don't pollute the system python.
VENV_DIR="${DOCLING_MODELS_VENV:-$(dirname "$0")/../.venv-docling-models}"
if [[ ! -d "$VENV_DIR" ]]; then
  echo "==> Creating fetch venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> Installing docling (pulls in the docling-tools CLI via the cli extra)"
pip install --quiet --upgrade pip
pip install --quiet \
    "docling[easyocr]>=2.80.0,<3.0.0"

echo "==> Downloading Docling artifacts (layout, table-former, picture-classifier, code-formula, OCR)"
docling-tools models download \
    layout \
    tableformer \
    tableformerv2 \
    picture_classifier \
    code_formula \
    easyocr \
    rapidocr \
    -o "$OUT_DIR"

echo "==> Done. Contents of $OUT_DIR:"
ls -1 "$OUT_DIR"

echo
echo "Next steps:"
echo "  - Build the Docker image: docker build -f document-parser/Dockerfile \\"
echo "        --target local -t docling-studio-backend:local ."
echo "    (the Dockerfile does the same download automatically)"
echo "  - OR mount this directory into the running container:"
echo "      -v \"$OUT_DIR:/opt/docling/models:ro\""
echo "    with env DOCLING_ARTIFACTS_PATH=/opt/docling/models"