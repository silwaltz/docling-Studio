# Documentation (docs)

## Purpose

Project documentation including architecture decisions (ADRs), design docs, audit framework, processes, community guidelines, and operational playbooks.

## Ownership

Documentation team owns structure and quality. Domain experts own content accuracy.

## Local Contracts

- **ADRs**: Follow `architecture/adr-template.md`, numbered sequentially
- **Design docs**: One doc per feature/decision, stored in `design/`
- **Audit framework**: Master audit in `audit/master.md`, individual audits in `audit/audits/`
- **Processes**: Index in `PROCESSES.md`, detailed docs in subdirectories
- **Markdown**: Use standard Markdown, no custom extensions
- **Diagrams**: Mermaid for architecture, store source in `.md` files

## Work Guidance

- **New ADR**: Copy `architecture/adr-template.md`, increment number, fill sections
- **Design doc**: Use issue number as prefix (e.g., `195-feature-name.md`)
- **Audit reports**: Store in `audit/reports/release-X.Y.Z/`
- **Process updates**: Update `PROCESSES.md` index when adding/removing processes
- **Links**: Use relative paths for internal docs, absolute URLs for external
- **Keep current**: Remove outdated docs, update stale references

## Verification

- Check all internal links resolve
- Verify ADR numbering is sequential
- Ensure PROCESSES.md index matches actual files

## Child DOX Index

- `architecture/` - ADRs, coding standards, architectural guidance
- `audit/` - Audit framework, reports, and individual audit docs
- `design/` - Feature design documents
- `community/` - Onboarding, issue triage, roadmap
- `git-workflow/` - Commit conventions, code review, merge policy
- `operations/` - Incident response, security, monitoring
- `release/` - Deployment, rollback playbooks
