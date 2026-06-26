# =============================================================================
# Pre-fetch Docling model artifacts to a local directory (PowerShell).
#
# Runs the same download the `docling-model-baker` stage runs inside the
# Dockerfile, but on the host — useful when:
#   - The build host is offline but a separate staging host has internet.
#   - You want to inspect what artifacts Docling expects before baking.
#   - You want to bind-mount the artifacts as a volume rather than bake.
#
# Usage:
#   .\scripts\fetch_docling_models.ps1 [-OutputDir <path>]
#     Default -OutputDir: .\docling-models
#
# Then either:
#   - bake into the image via the Dockerfile (default), OR
#   - mount into the running container:
#       volumes:
#         - .\docling-models:/opt/docling/models:ro
#       environment:
#         DOCLING_ARTIFACTS_PATH: /opt/docling/models
# =============================================================================
[CmdletBinding()]
param(
    [string]$OutputDir = "docling-models"
)

$ErrorActionPreference = "Stop"

# Resolve to absolute path
$OutputDir = (Resolve-Path -Path $OutputDir -ErrorAction SilentlyContinue) ?? (New-Item -ItemType Directory -Force -Path $OutputDir)
$OutputDir = (Resolve-Path $OutputDir).Path

Write-Host "==> Pre-fetching Docling model artifacts to: $OutputDir"

# Use a dedicated venv so we don't pollute the system python.
$VenvDir = Join-Path (Split-Path $PSScriptRoot -Parent) ".venv-docling-models"
if (-not (Test-Path $VenvDir)) {
    Write-Host "==> Creating fetch venv at $VenvDir"
    python -m venv $VenvDir
}
& "$VenvDir\Scripts\Activate.ps1"

Write-Host "==> Installing docling (pulls in the docling-tools CLI via the cli extra)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet `
    "docling[easyocr]>=2.80.0,<3.0.0"

Write-Host "==> Downloading Docling artifacts (layout, table-former, picture-classifier, code-formula, OCR)"
docling-tools models download `
    layout `
    tableformer `
    tableformerv2 `
    picture_classifier `
    code_formula `
    easyocr `
    rapidocr `
    -o $OutputDir

Write-Host "==> Done. Contents of $OutputDir:"
Get-ChildItem $OutputDir | Select-Object Name

Write-Host ""
Write-Host "Next steps:"
Write-Host "  - Build the Docker image: docker build -f document-parser/Dockerfile ``
    --target local -t docling-studio-backend:local ."
Write-Host "    (the Dockerfile does the same download automatically)"
Write-Host "  - OR mount this directory into the running container:"
Write-Host "      -v `"$OutputDir`:/opt/docling/models:ro`""
Write-Host "    with env DOCLING_ARTIFACTS_PATH=/opt/docling/models"