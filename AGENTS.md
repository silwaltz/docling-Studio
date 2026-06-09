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
- **LLM**: Ollama (local) for document Q&A

## User Preferences

When the user requests a durable behavior change, record it here or in the relevant child AGENTS.md

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
  - `operations/` - Incident response, security, monitoring
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