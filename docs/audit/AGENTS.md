# Audit Framework (audit)

## Purpose

Quality audit framework with master audit orchestration, individual audit checklists, and release audit reports.

## Ownership

QA team owns audit framework and execution. Domain experts contribute to audit criteria.

## Local Contracts

- **Master audit**: `master.md` orchestrates all 12 audits for release gate
- **Individual audits**: One file per audit axis in `audits/`
- **Reports**: Stored in `reports/release-X.Y.Z/` with summary and per-audit findings
- **Severity**: CRIT (blocks release), MAJ (must fix), MIN (nice to have), INFO
- **Re-audit**: Required after fixing CRIT/MAJ findings

## Work Guidance

- **Full audit**: Follow `master.md` for release branches
- **Single audit**: Run individual audit from `audits/` for targeted checks
- **Report format**: Use template from `master.md`, include severity, finding, location, recommendation
- **Automated checks**: Run `profiles/fastapi-vue/commands.sh` before manual audit
- **Findings**: Document in `reports/release-X.Y.Z/NN-audit-name.md`
- **Summary**: Aggregate all findings in `reports/release-X.Y.Z/summary.md`

## Verification

- All 12 audits completed for release
- CRIT findings resolved before merge
- Summary report includes verdict (GO/GO CONDITIONAL/NO-GO)

## Child DOX Index

- `audits/` - Individual audit checklists (12 audits)
- `reports/` - Release audit reports by version
