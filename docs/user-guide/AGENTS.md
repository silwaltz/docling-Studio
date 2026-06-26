# User Guides (user-guide)

## Purpose

Client-facing deployment and usage guides. These docs are written for the customer's engineers (often junior) who receive a built artifact and need to deploy it themselves — as opposed to internal design / release docs that target our own team.

## Ownership

Project lead writes and maintains these. Domain experts review technical accuracy before each release. Updates are mandatory whenever the deployment contract changes.

## Local Contracts

- **Audience**: customer's deployment / DevOps engineer. Junior-friendly.
- **Language**: 中英對照 (bilingual Chinese-English). Technical terms, commands, file paths, and env var names stay in English.
- **Tone**: step-by-step, command-first, explains WHY not just WHAT.
- **Code blocks**: copy-pasteable. Real commands, real example values, placeholders clearly marked with `<ANGLE_BRACKETS>`.
- **Diagrams**: Mermaid for flowcharts / network diagrams. Inline ASCII for short lists.
- **Versioning**: every guide has a "Last verified against" line with image tag + commit SHA. Update when the contract changes.

## Work Guidance

- **Structure**: 介紹 → 前置準備 → 步驟 (numbered) → 驗證 → 常見問題 → 附錄.
- **Traps / gotchas**: surface them inline in the relevant step AND collect them in a final "常見問題" section.
- **Verification commands**: every step that mutates state must include a one-liner to verify it worked.
- **Cross-platform**: prefer commands that work on both Linux/Mac bash and Windows PowerShell. If they differ, show BOTH.
- **No marketing fluff**: skip "powerful", "easy", "revolutionary". Show the command.

## Verification

- All commands in the guide actually run (verified on a clean host before merging).
- Placeholders (`<...>`) are flagged — no half-filled values.
- Internal links to design docs / ADRs work.

## Child DOX Index

- `airgap-deployment-guide.md` — offline build + air-gapped deployment walkthrough (clone → build → transfer → .env → up)
