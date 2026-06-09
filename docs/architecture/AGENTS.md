# Architecture Documentation (architecture)

## Purpose

Architecture Decision Records (ADRs), coding standards, and architectural guidance for the project.

## Ownership

Architecture team owns ADR process and standards. Domain experts contribute ADRs for their areas.

## Local Contracts

- **ADR format**: Follow `adr-template.md`, numbered sequentially (ADR-001, ADR-002, etc.)
- **ADR storage**: All ADRs in `adrs/` subdirectory
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Immutability**: Accepted ADRs are immutable, supersede instead of editing
- **Coding standards**: `coding-standards.md` defines project-wide conventions

## Work Guidance

- **New ADR**: Copy `adr-template.md` to `adrs/ADR-NNN-title.md`, increment number
- **ADR sections**: Context, Decision, Consequences, Status
- **Superseding**: Create new ADR, update old ADR status to "Superseded by ADR-NNN"
- **Standards updates**: Update `coding-standards.md` when team agrees on new conventions
- **Review**: All ADRs require team review before acceptance

## Verification

- ADR numbers are sequential
- All ADRs follow template structure
- No gaps in ADR numbering

## Child DOX Index

- `adrs/` - Architecture Decision Records
