# CI/CD Workflows (.github)

## Purpose

GitHub Actions workflows for continuous integration, release automation, security scanning, and issue management.

## Ownership

DevOps team owns workflow definitions, CI/CD pipeline, and release automation.

## Local Contracts

- **CI workflow**: Runs on every PR (lint, test, build)
- **Release gate**: Runs on `release/*` branches and PRs to `main`
- **Release workflow**: Triggered by version tags (`vX.Y.Z`)
- **Auto-close issues**: Closes stale issues after 30 days
- **Docling compat**: Tests against latest Docling versions
- **Security**: Trivy scans, dependency audits

## Work Guidance

- **New workflow**: Add `.yml` file in `workflows/`, follow existing naming
- **Secrets**: Use GitHub secrets for credentials, never hardcode
- **Caching**: Cache dependencies (pip, npm) to speed up builds
- **Artifacts**: Upload test reports, build artifacts for debugging
- **Notifications**: Use workflow status checks, avoid noisy notifications
- **Testing**: Test workflow changes on feature branches before merge

## Verification

- Workflows must pass on feature branches before merge
- Release gate must show GO verdict before merging release PR
- Check workflow runs in GitHub Actions tab

## Child DOX Index

- `workflows/` - GitHub Actions workflow definitions
- `ISSUE_TEMPLATE/` - Issue templates for bugs and features
