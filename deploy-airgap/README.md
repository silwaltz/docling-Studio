# Docling Studio — Air-Gap Deployment (Single Linux Machine)

This folder is the **deployable artifact** for an air-gapped Docling Studio installation that runs the entire stack — vLLM + backend + frontend — on **one** Linux host with an NVIDIA GPU.

It corresponds to the minimal setup of `docs/user-guide/airgap-deployment-guide.md` (§ 15.6), with the addition of a co-located vLLM server.

## What's inside

```
deploy-airgap/
├── Dockerfile.vllm             # Multi-stage: bakes Qwen3-VL-8B-AWQ-4bit into vllm/vllm-openai
├── docker-compose.yml          # vllm + document-parser + frontend on one compose project
├── .env.example                # Template; copy to .env and fill <ANGLE_BRACKETS>
├── export-bundle.sh            # Build host: build + verify + save + gzip + sha256
├── README.md                   # This file
└── bundle/                     # After running export-bundle.sh: the transfer artifacts
    ├── vllm.tar.gz
    ├── backend.tar.gz
    ├── frontend.tar.gz
    └── bundle.sha256
```

## Architecture

```
Browser ──HTTP──> :3000 ──> frontend (nginx + Vue)
                              │
                              └──> :8000 document-parser (FastAPI + Docling)
                                          │
                                          ├──> /app/uploads, /app/data  (Docker volumes)
                                          │
                                          └──HTTP──> vllm:8000 (Qwen3-VL-8B-AWQ-4bit)
                                                       │
                                                       └──> GPU (NVIDIA, 16 GB+)
```

All three services share one Docker network (created automatically by compose). The backend reaches vLLM via the in-network DNS name `vllm:8000` — no host port is published for vLLM, so it can't be reached from outside the compose project.

## What the air-gap host needs

- 3 images loaded from the build-host bundle:

| Image | Uncompressed on disk | Compressed |
|---|---|---|
| `docling-studio-vllm:offline` | ~17 GB (10 GB vLLM base + 7 GB model) | ~9-10 GB gzipped |
| `docling-studio-backend:offline` | ~17 GB (with baked Docling models) | ~6 GB gzipped |
| `docling-studio-frontend:offline` | ~95 MB | ~26 MB gzipped |

- One `docker-compose.yml` (this folder).
- One `.env` (copy `.env.example`, fill in `<ANGLE_BRACKETS>`).
- Hardware: 1× NVIDIA GPU with ≥ 16 GB VRAM, ≥ 64 GB system RAM, ≥ 100 GB free disk, Linux + Docker 24+ + `nvidia-container-toolkit`.

## Quick start on the air-gap host

```bash
# 0. One-time host prereqs (skip if already done):
#    - NVIDIA driver R535+ (R555+ recommended for consumer GeForce)
#    - Docker 24+ with the nvidia runtime wired up:
#        sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker
#    - Smoke-test GPU passthrough:
#        docker run --rm --gpus all nvidia/cuda:12.6.0-base nvidia-smi

sudo mkdir -p /opt/docling-studio && sudo chown $USER:$USER /opt/docling-studio
cd /opt/docling-studio

# 1. Copy docker-compose.yml + .env.example (and bundle/) from this folder.
cp /path/from/build/host/docker-compose.yml .
cp /path/from/build/host/.env.example .env
# .env is ready as-is for the minimal stack — no fields to fill in.
# (If you later add Neo4j/OpenSearch, also set STORE_SECRET_KEY — see below.)

# 2. Load the three images.
sha256sum -c bundle/bundle.sha256
gunzip -k bundle/*.tar.gz
docker load -i bundle/vllm.tar
docker load -i bundle/backend.tar
docker load -i bundle/frontend.tar
rm bundle/*.tar

# 3. Bring it up. vLLM takes 5-10 min on first boot (model load + CUDA graphs).
docker compose up -d
docker compose ps                          # vllm turns healthy after model load
docker compose logs -f vllm                # wait for "Application startup complete."

# If you are running on Docker Desktop / WSL2, the vLLM service also needs
# VLLM_WSL2_ENABLE_PIN_MEMORY=1 (already set in docker-compose.yml).

# 4. Smoke-test the full stack.
curl http://localhost:8002/api/health
docker exec docling-studio-backend python -c "import urllib.request; print(urllib.request.urlopen('http://vllm:8000/v1/models').read().decode())"
# Should list: {"data":[{"id":"qwen3-vl:8b-instruct",...}]}

# Open http://localhost:3000 in a browser.
```

## .env fields to fill in

**Nothing is required.** The whole file is pre-configured for a co-located vLLM with no ingestion. The one optional knob:

| Variable | When to set | Notes |
|---|---|---|
| `STORE_SECRET_KEY` | Only if you later set a Neo4j/OpenSearch password in the UI | Fernet key for sealing store credentials. Boot fails closed only when the `stores` table has a non-null `connection_password_sealed` value. Leave blank for the minimal stack. Generate via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`; keep stable across redeployments. |

Everything else is pre-set for the co-located vLLM. Specifically:
- `OPENAI_BASE_URL=http://vllm:8000/v1` (in-network DNS, not a host port)
- `VLM_OPENAI_URL=http://vllm:8000/v1/chat/completions`
- `CHAT_MODEL_ID=qwen3-vl:8b-instruct` (matches the alias vLLM serves)
- `CHAT_PROVIDER=openai` (do not change to `ollama` — there is no Ollama here)

## What's intentionally NOT in this setup

- **No** `embedding` / `opensearch` / `neo4j` services (no ingestion, no RAG, no graph).
- **No** `OPENSEARCH_URL`, `EMBEDDING_URL`, `NEO4J_*` env vars.

If the operator later wants search / graph queries, see the airgap guide § 15.6 for the upgrade path.

## Build-host repro

To rebuild the bundle from scratch (online, one time):

```bash
./export-bundle.sh
```

That single script:

1. Builds `docling-studio-vllm:offline` (pulls `vllm/vllm-openai:latest` for amd64, downloads Qwen3-VL-8B-AWQ-4bit from HF, bakes both into the image).
2. Builds `docling-studio-backend:offline` (for amd64, with all Docling models baked).
3. Builds `docling-studio-frontend:offline` (for amd64).
4. Runs the no-network converter check on the backend image.
5. Lists the HF cache layout on the vLLM image to prove the model is baked.
6. `docker save`s each image, `gzip`s, and emits `bundle.sha256`.

> **Why `--platform linux/amd64` everywhere?** The air-gap host is x86_64 Linux. On an Apple Silicon build host, `onnxruntime-gpu` (backend) and most vLLM wheels are x86_64-only — building natively as `linux/arm64` fails. Buildx cross-compiles via QEMU.

## Source

Generated from commit `0bde584` on `feat/vllm-inference-engine`. The vLLM service definition and image pin are adapted from `docs/operations/vllm-rhel-install/docker-compose.yml` (the operator-only "vLLM on a separate RHEL host" recipe).
