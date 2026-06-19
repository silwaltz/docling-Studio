# Installing docling-studio's vLLM inference backend on RHEL — Docker guide

This guide installs the **vLLM** inference engine on **RHEL 9.x with Docker** so
docling-studio can run its Ask pipeline (text chat) and VLM pipeline (page-image
extraction) against a single, GPU-backed, OpenAI-compatible HTTP server.

The docling-studio project itself needs no code changes — point its
`OPENAI_BASE_URL` and `VLM_OPENAI_URL` at the vLLM container's host:port and
flip `CHAT_PROVIDER=openai`. The shipped `docker-compose.dev.yml` already wires
this up, so most users can skip this guide and just run:

```bash
docker compose -f docker-compose.dev.yml up -d
```

…on a Linux host with an NVIDIA GPU and a working `nvidia-container-toolkit`.

This guide exists for the case where vLLM lives on a **separate RHEL host**
(GPU server, a beefy workstation, or a node in a cluster) and docling-studio
runs elsewhere on the network — i.e. you can't co-locate them in one
`docker compose` project. It also covers the prereq install for any RHEL 9.x
host that hasn't been set up yet.

The companion files in `docs/operations/vllm-rhel-install/` are:

| File | Purpose |
|---|---|
| `install-vllm-rhel.sh` | RHEL 9 prereqs + Docker + NVIDIA toolkit + GPU smoke test + image pull |
| `verify-vllm-rhel.sh` | End-to-end smoke test (6 checks against the running vLLM) |
| `docker-compose.yml` | Single-service orchestration: one `vllm` container |

This revision follows the official vLLM Docker install at
<https://docs.vllm.ai/en/latest/getting_started/installation/gpu/>.

```
+--------------+        +-----------------+        +------------------+
| docling-     | HTTP   |  vLLM container |  GPU   |  Qwen3-VL-8B-    |
| studio       +------->+  :8000 OpenAI   +------->+  Instruct-AWQ-4  |
| container    |        |  /v1/chat/...   |        |  (~7.4 GB VRAM)   |
+--------------+        +-----------------+        +------------------+
   OPENAI_BASE_URL=...:8000/v1    single model serves BOTH Ask + VLM
```

## 1. What docling-studio actually calls

We grepped the project for `ollama`, `11434`, `/api/`, and `/v1/` and confirmed
the project talks to the LLM via exactly two HTTP endpoints:

| Endpoint | Used by | Format |
|---|---|---|
| `POST /v1/chat/completions` (Ask) | `document-parser/api/chat.py` (when `CHAT_PROVIDER=openai`) | OpenAI JSON / SSE |
| `POST /v1/chat/completions` (VLM) | `document-parser/infra/local_converter.py:468` | OpenAI JSON / SSE |
| `GET  /v1/models` | `infra/llm/ollama_provider.py` health check, `/ollama-status` | OpenAI JSON |

Both endpoints are **OpenAI-compatible** out of the box, which is exactly what
vLLM serves natively. No translation bridge, no `/api/chat` NDJSON — the Ask
pipeline was migrated to OpenAI shape when the single-model setup landed
(2026-06-19), and the VLM path always used OpenAI shape.

So the entire job is: stand up one `vllm/vllm-openai` container that serves
Qwen3-VL-8B-Instruct-AWQ-4bit under the alias `qwen3-vl:8b-instruct`, expose it
on host port 8000, and point docling-studio at it.

## 2. Hardware requirements

Single-model, AWQ-4bit quantized. The whole stack fits on one 16 GB card:

| Model | Quant | Approx VRAM | Min GPU | Recommended |
|---|---|---|---|---|
| `cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit` | AWQ-4bit | ~7.4 GB weights + 4-5 GB KV cache @ 24 k ctx ≈ **13.8 GB** total | L4 24 GB / A10 24 GB / RTX 5060 Ti 16 GB @ ctx ≤ 24 k | A100 40 GB / L40S 48 GB for headroom or 32 k ctx |

System RAM: ≥ 64 GB. HF cache + vLLM activations + CUDA shm all want headroom.
Storage: ≥ 200 GB free for the HF cache (one model ≈ 8 GB on disk; the cache
also holds tokenizer assets, configs, and any future model variants you load
via `--served-model-name` aliases).

If you have multiple GPUs, the single container can still pin to one — set
`count: 1` under `deploy.resources.reservations.devices` and add
`NVIDIA_VISIBLE_DEVICES=0` to the environment to make it explicit.

## 3. RHEL 9.x software prerequisites

### 3.1 RHEL subscription
```bash
sudo subscription-manager register --auto-attach
sudo subscription-manager repos --enable rhel-9-for-x86_64-baseos-rpms \
                                 --enable rhel-9-for-x86_64-appstream-rpms
```

### 3.2 NVIDIA driver
**Required: ≥ R535 (CUDA 12.2). R555+ recommended.**

The vLLM Docker image bundles **CUDA 12.9** plus the **NVIDIA CUDA
compatibility libraries**, so the host driver can be older than the image's
CUDA — just set `VLLM_ENABLE_CUDA_COMPATIBILITY=1` in the container env.
The compat shim only supports professional / datacenter GPUs (A100, L4, L40S,
H100, etc.); consumer GeForce cards need a matching-or-newer host driver.

The install script uses `kmod-nvidia` from the `negativo17` EPEL-NVIDIA repo,
which ships newer drivers than RHEL's bundled ones. After the first install
run, **reboot before continuing** — the nouveau driver has to be blacklisted
and the nvidia kernel module loaded before vLLM will work.

### 3.3 CUDA toolkit
**NOT required on the host.** The vLLM Docker image (`vllm/vllm-openai`) ships
its own CUDA 12.9 toolchain plus cuDNN, NCCL, and PyTorch. Skip the host CUDA
install entirely.

### 3.4 Docker + NVIDIA Container Toolkit
The script installs:
- `docker-ce` + `docker-ce-cli` + `containerd.io` + `docker-buildx-plugin` + `docker-compose-plugin`
  from Docker's official RHEL repo.
- `nvidia-container-toolkit` from NVIDIA's RHEL repo, then runs
  `nvidia-ctk runtime configure --runtime=docker` so Docker knows about
  `--gpus`.

**Smoke-test after install** (the script runs this for you):
```bash
docker run --rm --gpus all nvidia/cuda:12.6.0-base nvidia-smi
```
If this prints your GPU table, you're good. If it errors with
`could not select device driver`, the toolkit isn't wired in — run
`nvidia-ctk runtime configure --runtime=docker && systemctl restart docker`.

## 4. Single-model, single-container layout

Unlike earlier dual-model setups (gemma for Ask + Qwen3-VL for VLM with an
Ollama-API bridge), this revision serves **both pipelines from one vLLM
container**. That works because:

- Qwen3-VL-8B is a vision-language model that **also accepts text-only
  messages** at `/v1/chat/completions`. The Ask pipeline sends text-only
  messages, gets text-only completions back, and never notices the model is
  multimodal.
- The VLM pipeline sends `image_url` content parts alongside text; the same
  model processes them and returns text. Same endpoint, same model.
- Both pipelines already speak OpenAI shape, so vLLM's native API is the
  common denominator — no translation layer needed.

The container name is **`vllm`** (was previously `vllm-ask` / `vllm-vlm` /
`vllm-bridge` in older setups — those service names are gone). The model is
served under the alias `qwen3-vl:8b-instruct` via `--served-model-name`, which
matches the model name docling-studio already references in its `.env`.

## 5. Prerequisites on a fresh RHEL 9.x host

One-time per host. Idempotent — safe to re-run. **Skip this section entirely**
if your host already has the NVIDIA driver, Docker CE, and
`nvidia-container-toolkit` wired up. You can verify with:

```bash
nvidia-smi                                                  # driver + GPU
docker run --rm --gpus all nvidia/cuda:12.6.0-base nvidia-smi  # GPU passthrough
```

If both work, jump straight to **Section 6**.

### 5.1 Copy the helper scripts onto the host

```bash
# From your workstation (a clone of the docling-studio repo)
scp -r docs/operations/vllm-rhel-install/ root@<rhel-host>:/root/

ssh root@<rhel-host>
cd /root/vllm-rhel-install
chmod +x install-vllm-rhel.sh verify-vllm-rhel.sh
```

### 5.2 Run the prereq installer

```bash
sudo ./install-vllm-rhel.sh
```

What it does (numbered phases, each idempotent):

1. Verify RHEL subscription + enable baseos / appstream / supplementary repos.
2. Install EPEL + base packages (`git`, `curl`, `firewalld`, `pciutils`, …).
3. **If `nvidia-smi` is missing**: install `kmod-nvidia` from the negativo17
   EPEL-NVIDIA repo, blacklist nouveau, regenerate initramfs, then **exit 0
   with a reboot hint** — return to step 5.3 below.
4. **If `nvidia-smi` already works**: install Docker CE + compose v2 plugin
   (Docker's official RHEL repo) + NVIDIA Container Toolkit (NVIDIA's RHEL
   repo), wire up the docker runtime via `nvidia-ctk`, restart dockerd.
5. Smoke-test GPU passthrough: `docker run --rm --gpus all
   nvidia/cuda:12.6.0-base nvidia-smi`. Fails the script if this errors with
   `could not select device driver`.
6. `docker pull vllm/vllm-openai:latest` (~10 GB, one-time).
7. Lay down `/opt/vllm/` + `/var/lib/vllm/hf-cache/` + `/var/log/vllm/`.
8. Open host port 8000/tcp via `firewalld` (or `iptables` if firewalld is off).
9. Write `/opt/vllm/.env` with the model tag + GPU-util knobs for the
   compose service to consume.

The script is **safe to re-run** after any partial failure — each phase
short-circuits if its target is already in place.

### 5.3 Reboot after the first driver install

If `install-vllm-rhel.sh` printed the reboot hint in step 3:

```bash
sudo systemctl reboot
ssh root@<rhel-host>
cd /root/vllm-rhel-install
sudo ./install-vllm-rhel.sh    # continues from step 4 onward
```

After this second pass you should see all 9 phases complete and a final "Done."
message with no further action required.

## 6. Stack bring-up

This is the repeatable, version-controlled part. **It is OS-agnostic** — the
same commands work on Ubuntu, Fedora, Rocky, or anywhere else that already has
the prerequisites from Section 5. Every step below assumes you've finished
Section 5 (or your host already had the prereqs).

### 6.1 Stage the compose file

```bash
sudo mkdir -p /opt/vllm
sudo cp /root/vllm-rhel-install/docker-compose.yml /opt/vllm/
```

### 6.2 (Optional) Override defaults in `.env`

`install-vllm-rhel.sh` already wrote `/opt/vllm/.env` with sensible 16 GB
defaults. Bump these for headroom:

| Variable | 16 GB default | 24 GB+ bump |
|---|---|---|
| `VLLM_MAX_MODEL_LEN` | `24576` | `32768` |
| `VLLM_GPU_MEM_UTIL` | `0.92` | `0.95` |

Edit `/opt/vllm/.env` directly, then re-run `docker compose up -d` (no
re-install needed — compose re-reads `.env` on every invocation).

### 6.3 Bring the stack up

```bash
cd /opt/vllm
sudo docker compose up -d                 # starts one `vllm` service
sudo docker compose ps                    # status; healthcheck turns green
                                          #   after model load + CUDA graphs
                                          #   (~5-10 min cold, ~30 s warm)
```

### 6.4 Wait for the vLLM service to become healthy

```bash
sudo docker compose logs -f vllm
#   "Application startup complete." + a healthy healthcheck ping  ← ready
```

The `start_period: 300s` on the compose healthcheck absorbs the cold-start
model load; the healthcheck itself pings `/v1/chat/completions` with
`max_tokens=1` so it only turns green after the engine is actually serving.

### 6.5 Smoke-test the full stack

```bash
cd /root/vllm-rhel-install
sudo ./verify-vllm-rhel.sh
```

Six checks (driver, compose stack, `/v1/models`, Ask text-only non-streaming,
Ask text-only streaming SSE, VLM text+image_url). Exits 0 only if all six
pass — re-run after any change.

### What the stack gives you

| Container | Host port | Purpose | Healthcheck |
|---|---|---|---|
| `vllm` | 8000 | Qwen3-VL-8B-AWQ-4bit, OpenAI API | `POST /v1/chat/completions` with `max_tokens=1` returns 200 |

That's it. One container, one port. First-boot time is dominated by vLLM model
download + load (~5–10 min on a fast link for cold start; ~30 s for warm
restart with the HF cache bind-mounted).

## 7. Pointing docling-studio at vLLM

In the project's `.env` (or `docker-compose.override.yml` on the **docling-studio
host**, which may be different from the vLLM host):

```dotenv
# LLM (Ask) — talk to vLLM's OpenAI-compatible endpoint
CHAT_PROVIDER=openai
CHAT_MODEL_ID=qwen3-vl:8b-instruct       # matches vLLM --served-model-name
OPENAI_BASE_URL=http://<vllm-host>:8000/v1
OPENAI_API_KEY=                          # vLLM doesn't require one; leave blank

# VLM (page-image extraction) — same vLLM, same alias
VLM_BACKEND=ollama                       # the backend enum name sticks; it
                                         # routes via VLM_OPENAI_URL below
VLM_OLLAMA_MODEL=qwen3-vl:8b-instruct
VLM_OPENAI_URL=http://<vllm-host>:8000/v1/chat/completions
```

If vLLM is on the **same** host as docling-studio (the common dev setup), you
can use the magic hostname `host.docker.internal:8000` (Docker Desktop / Docker
Engine on Linux with the `host.docker.internal` bridge enabled) instead of
`<vllm-host>`. The shipped `docker-compose.dev.yml` uses exactly that.

Restart the docling-studio backend:

```bash
docker compose -f docker-compose.dev.yml restart document-parser
```

Verify from inside the docling-studio container:

```bash
docker compose -f docker-compose.dev.yml exec document-parser \
    curl -s http://host.docker.internal:8000/v1/models
# Should list: {"data":[{"id":"qwen3-vl:8b-instruct",...}]}

docker compose -f docker-compose.dev.yml exec document-parser \
    curl -s http://host.docker.internal:8000/v1/chat/completions \
      -H 'Content-Type: application/json' \
      -d '{"model":"qwen3-vl:8b-instruct","messages":[{"role":"user","content":"Reply with READY"}],"max_tokens":8}'
# Should echo "READY" inside a {"choices":[{"message":{"content":"READY"}}]} envelope
```

The UI's `/ollama-status` indicator (now actually an `/v1/models` status check
behind the scenes) turns green, and both the Ask feature and the VLM pipeline
route through the same vLLM server.

## 8. The fallback script (`scripts/start-vllm-qwen.sh`)

For developers running vLLM **outside** a `docker compose` project — e.g.
pointing the script at a bare `docker run`, or running it on a workstation
that doesn't share the project's compose network — the repo ships
`scripts/start-vllm-qwen.sh` and its Python twin `scripts/start_vllm_qwen.py`
at the project root. Both:

- Use the same image, model, and `--served-model-name` as the compose service.
- Bind-mount the HF cache so the model survives restarts.
- Expose port 8000 with `--gpus all` and `--ipc=host`.

If you ran the bundle installer and `docker compose up -d` in `/opt/vllm` is
already serving vLLM, you do **not** need to run the script — both target the
same port and the second one will fail to bind. Use one or the other.

## 9. What to expect after the swap

| Symptom | Likely cause | Fix |
|---|---|---|
| `curl http://<host>:8000/v1/models` hangs | vLLM still loading model (5-10 min on cold start) | `docker compose logs -f vllm`; wait for "Application startup complete" |
| `curl http://<host>:8000/v1/models` returns connection refused | Container crashed; check `docker compose ps` | `docker compose logs vllm` |
| Ask returns empty / mid-doc truncation | `--max-model-len` too small for the document | Bump `--max-model-len` in compose, `docker compose up -d` |
| `CUDA out of memory` in vLLM logs | 32 k context on 16 GB card; KV cache won't fit | Drop to `--max-model-len=24576 --gpu-memory-utilization=0.92` (the shipped defaults) |
| `could not select device driver` from `docker run --gpus all` | nvidia-container-toolkit not wired in | `nvidia-ctk runtime configure --runtime=docker && systemctl restart docker` |
| First request after startup is very slow | vLLM compiles CUDA graphs on first call | One-time warm-up; send a dummy request after start |
| `HF_TOKEN` missing for gated model | Some Qwen variants require accepting a license | `export HF_TOKEN=<your-token>` in `/opt/vllm/.env`, `docker compose up -d` |
| Older driver + new image fails on consumer GPU | CUDA compat libs only support datacenter GPUs | Upgrade host driver to R555+, or pin a `vllm-openai` image matching your CUDA |
| `port 8000 already in use` when binding vLLM | Another container (e.g. docling-studio on `8000:8000`) is already on it | Move docling-studio to `8002:8000` (the `docker-compose.dev.yml` default), then retry |
| VLM request returns content with `null` instead of a string (Deep Extract path) | vLLM's CoT mode in Qwen3-VL puts the answer in `reasoning` and emits `content: null` | Known issue (2026-06-19, unfixed). Either pass `"chat_template_kwargs": {"enable_thinking": false}` per request, or run vLLM with `--enable-in-reasoning` and a `reasoning-parser`. The merge still works (just without the VLM-direct contribution). |

## 10. Performance tuning knobs

The shipped compose defaults are tuned for the project's reference setup
(16 GB RTX 5060 Ti):

| Flag | Default | Why |
|---|---|---|
| `--model` | `cyankiwi/Qwen3-VL-8B-Instruct-AWQ-4bit` | AWQ-4bit fits on 16 GB; bf16 doesn't |
| `--served-model-name` | `qwen3-vl:8b-instruct` | Matches docling-studio's existing model name |
| `--max-model-len` | `24576` | KV cache for 32 k OOMs at 0.85 utilization on 16 GB |
| `--gpu-memory-utilization` | `0.92` | Leaves ~8 % headroom for activations on 16 GB |
| `--limit-mm-per-prompt` | `{"image":1}` | One page image per VLM call |
| `--dtype` | `auto` | Picks AWQ for this quant model |

If your GPU has more VRAM (24 GB+), you can bump:

- `--max-model-len` to `32768` for longer documents.
- `--gpu-memory-utilization` to `0.95` (some headroom loss; OOM risk).
- `--limit-mm-per-prompt` to `{"image":4}` to batch more pages per call.

Other useful flags:

- `--enforce-eager` — skip CUDA-graph capture; faster startup, ~5–15 % slower
  steady-state. Use only for development.
- `--enable-prefix-caching` — caches the Ask system prompt (it's huge) across
  requests. vLLM warns this can use more RAM.
- `--max-num-seqs` (default 32) — raise to 64 for higher concurrency if VRAM
  permits.

HF cache lives in `${HF_CACHE_DIR:-/var/lib/vllm/hf-cache}` so model files
survive `docker compose down`. Wipe with `docker compose down -v` if you need
a clean reload.

## 11. Smoke test reference

`verify-vllm-rhel.sh` covers:

1. `nvidia-smi` (driver + GPU).
2. `docker compose ps` (the `vllm` service running/healthy).
3. vLLM `/v1/models` reachable on port 8000.
4. vLLM `/v1/chat/completions` (Ask-style text-only request, non-streaming).
5. vLLM `/v1/chat/completions` (Ask-style text-only request, streaming SSE).
6. vLLM `/v1/chat/completions` (VLM-style request with an `image_url` part —
   uses a tiny inline base64 PNG so it works without any extra files).

The script exits 0 only if all six pass. Re-run after any change.

## 12. File inventory

This document lives at `docs/operations/vllm-rhel-installation.md`. Its
companion scripts ship alongside it in `docs/operations/vllm-rhel-install/`:

| Path | Purpose |
|---|---|
| `docs/operations/vllm-rhel-installation.md` | This document |
| `docs/operations/vllm-rhel-install/install-vllm-rhel.sh` | RHEL 9 prereqs + Docker + toolkit + GPU smoke test + image pull |
| `docs/operations/vllm-rhel-install/verify-vllm-rhel.sh` | End-to-end smoke test (6 checks) |
| `docs/operations/vllm-rhel-install/docker-compose.yml` | Single-service orchestration: one `vllm` container |

When you run the bundle installer (`install-vllm-rhel.sh`) the `.env`,
firewall rules, and HF cache are written to `/opt/vllm/` on the target
RHEL host — that is **not** the repo path; it's the deployment path
on the GPU server.

## 13. Rollback

If something goes wrong, point docling-studio's `.env` back at a local
Ollama (or another OpenAI-compatible endpoint):

```dotenv
CHAT_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434        # or wherever Ollama runs
OPENAI_BASE_URL=
VLM_OPENAI_URL=
```

You can keep both Ollama and vLLM installed side-by-side; only the
`CHAT_PROVIDER` and base URLs differ. To stop the vLLM stack:

```bash
cd /opt/vllm
sudo docker compose down    # keeps HF cache volume
sudo docker compose down -v # also wipes HF cache
```

## 14. Why this works (zero project code changes)

The migration is purely **deployment-side**:

- The project's `local_converter.py` VLM call already uses OpenAI's
  `/v1/chat/completions`, which vLLM serves natively.
- The project's `api/chat.py` Ask call flips to OpenAI shape when
  `CHAT_PROVIDER=openai`; vLLM serves the same shape.
- vLLM's `--served-model-name=qwen3-vl:8b-instruct` aliases the HF model ID to
  the model name the project already references.
- Both pipelines hit the same `vllm` container on host port 8000; the
  `document-parser` service reaches it via Docker's host bridge
  (`host.docker.internal:8000` when co-located, or a routable `<vllm-host>:8000`
  when split across hosts).

Result: the project runs unchanged. The operational delta vs. the old
Ollama + gemma setup is faster inference (vLLM's continuous batching +
PagedAttention), single model covering both pipelines (one less thing to
download / load / version-pin), and a much simpler compose topology
(one container, not three).