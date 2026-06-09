# Design Documents (design)

## Purpose

Feature design documents describing implementation approach, technical decisions, and trade-offs for specific features or issues.

## Ownership

Feature owners create and maintain design docs for their features.

## Local Contracts

- **Naming**: `{issue-number}-feature-name.md` (e.g., `195-copy-paste-image.md`)
- **Content**: Problem statement, proposed solution, alternatives considered, implementation notes
- **Status**: Draft, Approved, Implemented, Obsolete
- **Updates**: Update design doc when implementation deviates from original design
- **Diagrams**: Use Mermaid for architecture diagrams, store source in doc

## Work Guidance

- **New design**: Create doc before implementation, get team review
- **Sections**: Problem, Solution, Alternatives, Implementation, Open Questions
- **Cross-references**: Link to related ADRs, issues, PRs
- **Keep current**: Mark as Implemented when feature ships, Obsolete if abandoned
- **Retrospective**: Add "What we learned" section after implementation

## Verification

- Design doc exists for all major features
- Status reflects current state
- Links to issues/PRs are valid

## Child DOX Index

None (flat structure, all design docs in this directory)
