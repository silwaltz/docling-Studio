# DOX framework

- DOX is highly performant AGENTS.md hierarchy installed here
- Agent must follow DOX instructions across any edits

## Core Contract

- AGENTS.md files are binding work contracts for their subtrees
- Work products, source materials, instructions, records, assets, and durable docs must stay understandable from the nearest applicable AGENTS.md plus every parent AGENTS.md above it

## Read Before Editing

1. Read the root AGENTS.md
2. Identify every file or folder you expect to touch
3. Walk from the repository root to each target path
4. Read every AGENTS.md found along each route
5. If a parent AGENTS.md lists a child AGENTS.md whose scope contains the path, read that child and continue from there
6. Use the nearest AGENTS.md as the local contract and parent docs for repo-wide rules
7. If docs conflict, the closer doc controls local work details, but no child doc may weaken DOX

Do not rely on memory. Re-read the applicable DOX chain in the current session before editing.

## Update After Editing

Every meaningful change requires a DOX pass before the task is done.

Update the closest owning AGENTS.md when a change affects:

- purpose, scope, ownership, or responsibilities
- durable structure, contracts, workflows, or operating rules
- required inputs, outputs, permissions, constraints, side effects, or artifacts
- user preferences about behavior, communication, process, organization, or quality
- AGENTS.md creation, deletion, move, rename, or index contents

Update parent docs when parent-level structure, ownership, workflow, or child index changes. Update child docs when parent changes alter local rules. Remove stale or contradictory text immediately. Small edits that do not change behavior or contracts may leave docs unchanged, but the DOX pass still must happen.

## Hierarchy

- Root AGENTS.md is the DOX rail: project-wide instructions, global preferences, durable workflow rules, and the top-level Child DOX Index
- Child AGENTS.md files own domain-specific instructions and their own Child DOX Index
- Each parent explains what its direct children cover and what stays owned by the parent
- The closer a doc is to the work, the more specific and practical it must be

## Child Doc Shape

- Create a child AGENTS.md when a folder becomes a durable boundary with its own purpose, rules, responsibilities, workflow, materials, or quality standards
- Work Guidance must reflect the current standards of the project or user instructions; if there are no specific standards or instructions yet, leave it empty
- Verification must reflect an existing check; if no verification framework exists yet, leave it empty and update it when one exists

Default section order:
- Purpose
- Ownership
- Local Contracts
- Work Guidance
- Verification
- Child DOX Index

## Style

- Keep docs concise, current, and operational
- Document stable contracts, not diary entries
- Put broad rules in parent docs and concrete details in child docs
- Prefer direct bullets with explicit names
- Do not duplicate rules across many files unless each scope needs a local version
- Delete stale notes instead of explaining history
- Trim obvious statements, repeated rules, misplaced detail, and warnings for risks that no longer exist

## Closeout

1. Re-check changed paths against the DOX chain
2. Update nearest owning docs and any affected parents or children
3. Refresh every affected Child DOX Index
4. Remove stale or contradictory text
5. Run existing verification when relevant
6. Report any docs intentionally left unchanged and why

## Project Overview

Docling Studio is a document analysis platform with FastAPI backend (hexagonal architecture), Vue 3 frontend (feature-based), and supporting services (embedding, Neo4j, OpenSearch). The project follows strict architectural boundaries, comprehensive testing, and release gate quality controls.

## Global Rules

- **Architecture**: Backend uses hexagonal (ports & adapters), frontend uses feature-based modules
- **Testing**: All tests must pass before merge (pytest 377+, Vitest 156+, E2E Karate)
- **Code quality**: Ruff (backend), ESLint+Prettier (frontend), TypeScript strict mode
- **Versioning**: Semantic versioning, git tags are source of truth
- **Branching**: Feature branches to `main`, release branches for freeze, hotfix from tags
- **Documentation**: ADRs for architecture, design docs for features, keep docs current
- **Security**: No hardcoded secrets, env vars for config, dependency audits in CI
- **API contract**: REST with camelCase JSON, DDD-granular routes (one route ≈ one domain op)
- **Release gate**: 12 audits + automated checks before merging release to `main`

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLite (aiosqlite), Docling, sentence-transformers
- **Frontend**: Vue 3, TypeScript, Pinia, Vue Router, Vite
- **Storage**: SQLite (metadata), file system (uploads), Neo4j (graph), OpenSearch (search)
- **Infrastructure**: Docker Compose, GitHub Actions, Nginx
- **Testing**: pytest, Vitest, Karate (API), Karate UI (browser)
- **LLM**: vLLM (OpenAI-compatible) on `:8000` serving Qwen3-VL-8B-Instruct-AWQ-4bit as `qwen3-vl:8b-instruct` — single model covers BOTH the Ask pipeline (text chat) and the VLM pipeline (vision). See `.env` and `scripts/start_vllm_qwen.py` for the launch command.

## User Preferences

- **Single-model solution (2026-06-19)**: 16 GB GPU constraint → one model only. The Ask pipeline and the VLM pipeline both go through the same vLLM OpenAI-compatible server on `:8000`. `CHAT_MODEL_ID=qwen3-vl:8b-instruct`, `OPENAI_BASE_URL=http://host.docker.internal:8000/v1`, `VLM_OPENAI_URL=http://host.docker.internal:8000/v1/chat/completions`. Container is named `vllm` (not `vllm-ask` / `vllm-vlm`). Ask latency on Doc2: 3.69s, 213 tokens, 10/10 4-section entities extracted (3 over-extracted on Goods — invoice line items).
- **Offline / air-gapped build (2026-06-26)**: Docling model artifacts (~3.5 GB: layout, TableFormer, TableFormerV2, picture classifier, code-formula, EasyOCR, RapidOCR) are pre-fetched at Docker BUILD time via `docling-tools models download <subset>` and baked into the image at `/opt/docling/models`. Runtime sets `DOCLING_ARTIFACTS_PATH=/opt/docling/models` + `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` so Docling never reaches the network. Build host needs internet ONCE per image; the deployed image works fully offline. Targeted subset (not `--all`) — drops ~25 GB of in-process VLMs (GraniteDocling, SmolVlm, Granite Vision, MLX variants, Nemotron-OCR) that the remote-Ollama VLM path doesn't need. See `docs/design/offline-deployment.md` (internal design) and `docs/user-guide/airgap-deployment-guide.md` (bilingual client-facing walkthrough: clone → build → transfer → .env → up).
- **Client-provided vLLM (2026-06-26)**: production target points `OPENAI_BASE_URL` / `VLM_OPENAI_URL` at the client's own vLLM server (same model alias `qwen3-vl:8b-instruct`, OpenAI shape). Local `vllm` compose service stays for dev/test only. Flip `.env` to switch deployments — no code change.
- **VLM Backend**: Default VLM backend is `ollama` (qwen3-vl:8b-instruct hosted on Ollama — note: NOT `qwen3-vl:8b`, which silently falls back to OCR) instead of `granite` (in-process transformers). Users can select per-analysis via frontend UI or set globally via `VLM_BACKEND` env var.
- **VLM Output Mode** (Ollama only): `vlm_output_mode` ∈ {`json` (default, extract the four canonical sections), `markdown` (extract everything, preserve structure as MD)}. Selectable per-analysis in the dialog's VLM pipeline options, or globally via prompt env var override. When `markdown` is selected, the Ask LLM pipeline still receives the document as `content_markdown` (same path as the standard pipeline).
- **Ask Feature**: System prompt configured to extract trade/shipping document data as a 4-section flat JSON object (`Company Name<n>`, `Address<n>`, `Shipping Information<n>`, `Goods Description<n>`). Frontend auto-detects and allows JSON download.
- **Deep Extract** (NEW 2026-06-13, v3 update 2026-06-13): new `extract_mode` ∈ {`standard` (default), `deep`} on `PipelineOptions`. Deep mode runs standard + Ask-LLM + VLM-direct-JSON, then unions + dedupes the two `content_json` outputs (loose dedup — preserves PDF spelling/wording verbatim, never collapses via substring). Toggle in Parse tab > + New analysis dialog. Hidden when "Force VLM Pipeline" is on. **+18.8pp on the 4-doc golden (87.8% vs 69% standard+Ask)** — see `extracted-json/deep_extract__SHIPPED_REPORT.md` (v2 history) and `extracted-json/deep_extract__FULL_REPORT.md` (v3 13-doc test, all completed, no stuck jobs). Requires Ollama + `qwen3-vl:8b-instruct`. Artifacts (ask_raw / ask_json / vlm_json / merged) are persisted to `/app/data/deep_extract_artifacts/` per run.
- **Stuck-job recovery** (NEW 2026-06-13): `main.py` `lifespan` sweeps RUNNING rows whose `created_at` is older than `2 * CONVERSION_TIMEOUT + 5min` and flips them to FAILED with an explanatory error message. The startup hook is wrapped in `try/except` so a sweep failure can never crash startup. `AnalysisResponse.is_stale` lets the UI flag stuck jobs in the race window before the next restart's sweep runs. See `domain/ports.py::AnalysisRepository.fail_stale_running`.

## Known Stack Gotchas

These are things that have bitten us and will bite again. Document once, never debug twice.

- **`DOCLING_ARTIFACTS_PATH` must point to the PARENT directory** (2026-06-26). When baking Docling models into the image, set `DOCLING_ARTIFACTS_PATH=/opt/docling/models` — the parent of the model folders (`ds4sd--docling-models/`, `EasyOcr/`, etc.), NOT one of the individual model subdirs. Pointing it at a single model folder causes "downloads disabled" errors. Reference: [docling-project/docling#2555](https://github.com/docling-project/docling/issues/2555).
- **One-shot bring-up (2026-06-19).** The vLLM container is now part of `docker-compose.dev.yml` (with its own healthcheck that pings `/v1/chat/completions` with `max_tokens=1`, `start_period=300s` for model load). Cold-start the whole stack with `docker compose -f docker-compose.dev.yml up -d` — no separate `scripts/start_vllm_qwen.py` step needed. The script is kept as a fallback for running vLLM outside the compose network. `depends_on.vllm.condition: service_healthy` makes the document-parser wait for the model to actually load before booting.
- **Deep Extract: VLM-direct step silently fails on vLLM (2026-06-19, unfixed).** When the VLM-direct step is invoked via the vLLM OpenAI endpoint, `infra/local_converter.py`'s HTTP patch logs `🔧 Error parsing/fixing response: object of type 'NoneType' has no len()` (line 219) and the run lands at `VLM JSON extraction: no page responses collected`. Result: `merged == ask_json` (no VLM-direct contribution), and the saved artifacts contain only `ask_raw` + `ask_json` + `merged` — no `vlm_json`. Standard + Ask still works, and the merge is still valid (just less coverage). To fix: investigate why the patch's `len(content)` / `len(reasoning)` calls fail (most likely vLLM returns a `content: null` field when the model is in `enable_in_reasoning` mode rather than the expected string) and consider using `vllm serve ... --enable-in-reasoning` or stripping nulls defensively.
- **Port 8000 conflict on Windows when running vLLM + dev compose.** `docker-compose.dev.yml` originally mapped `8000:8000` for the document-parser, which collides with the vLLM OpenAI server on `:8000`. Now remapped to `8002:8000` (host → container). Frontend's `VITE_API_PROXY_TARGET` still uses the in-network name `http://document-parser:8000` and is unaffected.
- **Qwen3-VL context window on 16 GB.** vLLM needs ~4.5 GiB KV cache for `max-model-len=32768`, more than the 0.85-utilization budget allows. The launched container runs at `max-model-len=24576` and `gpu-memory-utilization=0.92` (see `scripts/start_vllm_qwen.py`). If you bump back to 32k, expect OOM on this GPU.
- **Qwen3-VL over-extracts on the Ask prompt** (vs Gemma4). On Doc2 the model emitted 4 `Goods Description` entries — 1 correct + 3 invoice line items (`100 PCT, VALUE OF GOODS SHIPPED`, `DEDUCTION OF ADVANCE PAYMENT`, `NET AMOUNT`). The `_SYSTEM_PROMPT` says "NO quantities / NO codes", but Qwen3-VL ignores that. Cross-check golden still 3/3 companies, 2/2 addresses, 1/1 shipping, 1/1 goods. Acceptable for the customization MVP; tighten the prompt or post-filter if precision matters.
- **`CHAT_MODEL_ID` env var is wrong in compose.** `docker-compose.yml` and `docker-compose.dev.yml` set `CHAT_MODEL_ID=gemma4:e4b` (no `-it-qat` suffix). Ollama only has `gemma4:e4b-it-qat`. The chat endpoint will return 404 from Ollama for every request unless either (a) the user types the correct model name in the Ask tab's model textbox, or (b) the request body includes `"model": "gemma4:e4b-it-qat"` explicitly. Fix the env var in compose, or accept the manual override. (Historical — current `.env` overrides to `qwen3-vl:8b-instruct`.)
- **Gemma4 streaming drops wrapping `{ }` ~50% of the time** and uses two other quirks: `"key<1>"` with angle brackets instead of `"key1"`, and `"key"="value"` with `=` instead of `:`. Frontend's `extractJson` in `DocAskTab.vue` only handles the brace-less case. See `experiments/reparse-saved.py` for the full set of fallbacks if you need to recover all 14 cases. (Historical — only relevant if you revert to the Gemma path.)
- **`\_` escapes in gemma4 output.** Spaces inside string values come back escaped as `\_`. Frontend has `cleanJsonForDownload` to strip them. Replicate in any offline parser. (Historical — only relevant if you revert to the Gemma path.)

## Child DOX Index

### Core Services

- **`document-parser/`** - FastAPI backend (hexagonal architecture)
  - `api/` - HTTP layer (routers, Pydantic schemas)
  - `domain/` - Pure domain logic (models, ports, value objects)
  - `services/` - Use case orchestration
  - `persistence/` - SQLite repositories
  - `infra/` - Infrastructure adapters (converters, chunker, LLM, Neo4j, settings)
    - `llm/` - LLM client adapters
    - `neo4j/` - Neo4j graph adapter
    - `secrets/` - Secret encryption utilities
  - `tests/` - pytest test suite (377+ tests)

- **`frontend/`** - Vue 3 SPA (feature-based architecture)
  - `src/app/` - App shell, router, global styles
  - `src/pages/` - Route-level page components
  - `src/features/` - Feature modules (analysis, chunking, document, etc.)
  - `src/shared/` - Cross-feature utilities (types, i18n, API client)

- **`embedding-service/`** - Standalone embedding microservice (FastAPI, sentence-transformers)

### Testing & Quality

- **`e2e/`** - End-to-end test suites (Karate)
  - `api/` - API test suite (Maven, Karate)
  - `ui/` - UI browser test suite (Maven, Karate UI)

### Documentation

- **`docs/`** - Project documentation
  - `architecture/` - ADRs, coding standards
    - `adrs/` - Architecture Decision Records
  - `audit/` - Audit framework and reports
    - `audits/` - Individual audit checklists (12 audits)
    - `reports/` - Release audit reports by version
  - `design/` - Feature design documents
  - `community/` - Onboarding, issue triage, roadmap
  - `git-workflow/` - Commit conventions, code review, merge policy
  - `operations/` - Incident response, monitoring, security, and infrastructure deployment guides
    - `vllm-rhel-installation.md` - RHEL 9 + Docker + vLLM (Qwen3-VL-AWQ-4bit) install guide for split-host deployments
    - `vllm-rhel-install/` - Companion scripts: `install-vllm-rhel.sh`, `verify-vllm-rhel.sh`, `docker-compose.yml`
  - `release/` - Deployment, rollback playbooks

### Infrastructure

- **`.github/`** - CI/CD workflows and issue templates
  - `workflows/` - GitHub Actions (CI, release gate, release, security)
  - `ISSUE_TEMPLATE/` - Bug and feature templates

### Configuration

- **Root level**: Docker Compose files, environment config, project metadata
  - `docker-compose.yml` - Production stack
  - `docker-compose.dev.yml` - Development stack with hot reload
  - `docker-compose.ingestion.yml` - Ingestion services only
  - `.env.example` - Environment variable template
  - `README.md` - Project overview and setup
  - `CONTRIBUTING.md` - Contribution guidelines
  - `CHANGELOG.md` - Version history