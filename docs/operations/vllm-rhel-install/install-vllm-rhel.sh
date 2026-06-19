#!/usr/bin/env bash
# install-vllm-rhel.sh - RHEL 9.x prerequisites + Docker + NVIDIA toolkit + vLLM image pull
#
# Single-model setup: Qwen3-VL-8B-Instruct-AWQ-4bit served by one `vllm` container
# on host port 8000, alias `qwen3-vl:8b-instruct`. docling-studio's Ask and VLM
# pipelines both point at this single endpoint via OPENAI_BASE_URL.
#
# Run as root (or with sudo). Tested on RHEL 9.4 / 9.5 with NVIDIA RTX 5060 Ti 16 GB,
# L4 24 GB, and A100 40 GB.
#
# This is the Docker-only install path matching the official vLLM docs at
# https://docs.vllm.ai/en/latest/getting_started/installation/gpu/
#
# Idempotent: safe to re-run after a partial failure.
#
# Usage:
#   sudo ./install-vllm-rhel.sh
#
# Optional environment overrides:
#   VLLM_IMAGE=vllm/vllm-openai:latest
#   VLLM_HF_MODEL=cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit
#   VLLM_MODEL_TAG=qwen3-vl:8b-instruct
#   VLLM_PORT=8000
#   HF_CACHE_DIR=/var/lib/vllm/hf-cache

set -euo pipefail

# ---------------------------------------------------------------------------
# 0. Configurable knobs
# ---------------------------------------------------------------------------
VLLM_IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:latest}"

# HuggingFace model ID (loaded by vLLM)
VLLM_HF_MODEL="${VLLM_HF_MODEL:-cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit}"

# Alias served by vLLM via --served-model-name (must match what docling-studio
# already uses in its .env: CHAT_MODEL_ID, VLM_OLLAMA_MODEL)
VLLM_MODEL_TAG="${VLLM_MODEL_TAG:-qwen3-vl:8b-instruct}"

# VRAM-aware defaults. 16 GB cards need --max-model-len=24576 + util=0.92.
# 24 GB+ cards can go back to 32 k; bump via env override.
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-24576}"
VLLM_GPU_MEM_UTIL="${VLLM_GPU_MEM_UTIL:-0.92}"

VLLM_PORT="${VLLM_PORT:-8000}"

INSTALL_DIR="/opt/vllm"
HF_CACHE_DIR="${HF_CACHE_DIR:-/var/lib/vllm/hf-cache}"
LOG_DIR="/var/log/vllm"

log()  { printf "\033[1;34m[install]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[install]\033[0m %s\n" "$*" >&2; }
fail() { printf "\033[1;31m[install]\033[0m %s\n" "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "Re-run as root: sudo $0"

# ---------------------------------------------------------------------------
# 1. RHEL subscription + base packages
# ---------------------------------------------------------------------------
log "Verifying RHEL subscription..."
if ! subscription-manager status >/dev/null 2>&1; then
    fail "No active RHEL subscription. Run: subscription-manager register --auto-attach"
fi
subscription-manager repos --enable "rhel-9-for-x86_64-baseos-rpms" \
                         --enable "rhel-9-for-x86_64-appstream-rpms" \
                         --enable "rhel-9-for-x86_64-supplementary-rpms" || true

log "Installing EPEL..."
dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

log "Installing base packages..."
dnf -y install \
    git curl wget ca-certificates tar bzip2 xz \
    python3 python3-pip \
    firewalld pciutils

# ---------------------------------------------------------------------------
# 2. NVIDIA driver (CUDA toolkit ships inside the vLLM container image -
#    only the host driver is needed)
# ---------------------------------------------------------------------------
log "Detecting GPU..."
if ! lspci | grep -qi 'nvidia'; then
    fail "No NVIDIA GPU detected on PCI bus. vLLM requires CUDA."
fi

if command -v nvidia-smi >/dev/null 2>&1; then
    DRIVER_VER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1)
    log "Existing NVIDIA driver: ${DRIVER_VER}"
    # Driver R555+ supports CUDA 12.5; vLLM's image uses CUDA 12.9 by default
    # but ships with cuda-compat libraries, so older drivers also work as long
    # as VLLM_ENABLE_CUDA_COMPATIBILITY=1 is set in the container.
    log "(Driver 535+ is the practical minimum; 555+ is recommended.)"
else
    log "Installing NVIDIA driver via EPEL-NVIDIA repo..."
    dnf config-manager --add-repo=https://negativo17.org/repos/epel-nvidia.repo || true
    dnf -y install kmod-nvidia nvidia-driver

    log "Blacklisting nouveau..."
    cat >/etc/modprobe.d/blacklist-nouveau.conf <<EOF
blacklist nouveau
options nouveau modeset=0
EOF
    dracut --force
    warn "Reboot required before continuing: run 'systemctl reboot' and re-execute this script."
    exit 0
fi

nvidia-smi || fail "nvidia-smi failed after driver install"

# ---------------------------------------------------------------------------
# 3. Docker + NVIDIA Container Toolkit (matches official vLLM Docker docs)
# ---------------------------------------------------------------------------
log "Installing Docker CE..."
if ! command -v docker >/dev/null 2>&1; then
    dnf config-manager --add-repo=https://download.docker.com/linux/rhel/docker-ce.repo
    dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable --now docker
else
    log "Docker already installed: $(docker --version)"
fi

# Verify compose v2 plugin is present (needed for deploy.resources syntax)
docker compose version >/dev/null 2>&1 || fail "docker compose v2 plugin not found. Install docker-compose-plugin."

log "Installing NVIDIA Container Toolkit..."
if ! command -v nvidia-ctk >/dev/null 2>&1; then
    curl -fsSL https://nvidia.github.io/libnvidia-container/stable/rpm/nvidia-container-toolkit.repo \
        | tee /etc/yum.repos.d/nvidia-container-toolkit.repo
    dnf -y install nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
else
    log "nvidia-container-toolkit already installed: $(nvidia-ctk --version)"
fi

# ---------------------------------------------------------------------------
# 4. Smoke-test GPU passthrough (the "hello world" of GPU containers)
# ---------------------------------------------------------------------------
log "Smoke-testing GPU access inside a container..."
docker run --rm --gpus all nvidia/cuda:12.6.0-base nvidia-smi \
    || fail "Container cannot see the GPU. Check nvidia-container-toolkit setup."

# ---------------------------------------------------------------------------
# 5. Pull the vLLM image (this can take a few minutes - ~10 GB)
# ---------------------------------------------------------------------------
log "Pulling vLLM image: ${VLLM_IMAGE}"
docker pull "${VLLM_IMAGE}"

# ---------------------------------------------------------------------------
# 6. Lay down the project layout
# ---------------------------------------------------------------------------
log "Creating project layout under ${INSTALL_DIR}..."
mkdir -p "${INSTALL_DIR}" "${HF_CACHE_DIR}" "${LOG_DIR}"

# ---------------------------------------------------------------------------
# 7. Firewall (open the vLLM port so docling-studio on a different host
#    can reach it)
# ---------------------------------------------------------------------------
log "Configuring firewalld (open ${VLLM_PORT}/tcp for the docling-studio host)..."
systemctl enable --now firewalld
firewall-cmd --permanent --add-port=${VLLM_PORT}/tcp
firewall-cmd --reload

# ---------------------------------------------------------------------------
# 8. Generate .env for docker compose (real .env, not just shell vars)
# ---------------------------------------------------------------------------
cat >"${INSTALL_DIR}/.env" <<EOF
# Generated by install-vllm-rhel.sh
VLLM_IMAGE=${VLLM_IMAGE}
VLLM_HF_MODEL=${VLLM_HF_MODEL}
VLLM_MODEL_TAG=${VLLM_MODEL_TAG}
VLLM_MAX_MODEL_LEN=${VLLM_MAX_MODEL_LEN}
VLLM_GPU_MEM_UTIL=${VLLM_GPU_MEM_UTIL}
VLLM_PORT=${VLLM_PORT}
HF_CACHE_DIR=${HF_CACHE_DIR}
EOF

log "Done."
log ""
log "Next steps:"
log "  1. Copy docker-compose.yml into ${INSTALL_DIR}/"
log "  2. cd ${INSTALL_DIR}"
log "  3. docker compose up -d                  # starts one 'vllm' service"
log "  4. docker compose logs -f vllm           # wait for 'Application startup complete'"
log "  5. cd <repo>/extracted-json/vllm-rhel-install && sudo ./verify-vllm-rhel.sh"
log "  6. On the docling-studio host, set in .env:"
log "       CHAT_PROVIDER=openai"
log "       CHAT_MODEL_ID=qwen3-vl:8b-instruct"
log "       OPENAI_BASE_URL=http://<vllm-host>:${VLLM_PORT}/v1"
log "       VLM_OPENAI_URL=http://<vllm-host>:${VLLM_PORT}/v1/chat/completions"
log ""
log "Notes:"
log "  - If your NVIDIA driver is older than R555, edit docker-compose.yml and"
log "    set VLLM_ENABLE_CUDA_COMPATIBILITY=1 in the vllm service environment."
log "  - First run pulls the model from HuggingFace. Set HF_TOKEN in"
log "    ${INSTALL_DIR}/.env if the model is gated."
log "  - On 16 GB cards keep the shipped defaults (max-model-len=24576,"
log "    gpu-memory-utilization=0.92). 24 GB+ cards can bump max-model-len to"
log "    32768 and gpu-memory-utilization to 0.95 via .env."
log "  - Use 'docker compose down' to stop; 'docker compose down -v' to wipe the HF cache volume."
log "  - The repo also ships scripts/start-vllm-qwen.sh as a fallback for"
log "    running vLLM outside a compose project (won't work if port ${VLLM_PORT}"
log "    is already bound by the compose service)."