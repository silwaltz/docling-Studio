# End-to-End Tests (e2e)

## Purpose

Karate-based E2E test suites for API and UI validation. Ensures critical user flows work end-to-end before release.

## Ownership

QA team owns test scenarios, maintenance, and CI integration. Developers contribute test coverage for new features.

## Local Contracts

- **Framework**: Karate for API tests, Karate UI for browser tests
- **Test data**: Generated via `generate-test-data.py` before test runs
- **Tags**: `@smoke`, `@regression`, `@e2e` for API; `@critical`, `@ui` for UI
- **Conventions**: Follow `CONVENTIONS.md` for test structure and naming
- **CI scope**: API runs all tags, UI runs `@critical` only
- **Local scope**: Full UI suite (`@ui`) runs locally before release

## Work Guidance

- **New API test**: Add feature file in `api/src/test/java/features/`
- **New UI test**: Add feature file in `ui/src/test/java/features/`
- **Test data**: Regenerate via `python e2e/generate-test-data.py` after schema changes
- **Tags**: Use `@smoke` for critical paths, `@regression` for edge cases
- **Assertions**: Prefer schema validation over field-by-field checks
- **Cleanup**: Tests must clean up created resources (documents, analyses)

## Verification

```bash
# Generate test data
python e2e/generate-test-data.py

# Start stack
docker compose up -d --wait

# API tests
mvn test -f e2e/api/pom.xml

# UI tests (critical)
mvn test -f e2e/ui/pom.xml -Dkarate.options="--tags @critical"
```

## Child DOX Index

- `api/` - Karate API test suite (Maven project)
- `ui/` - Karate UI browser test suite (Maven project)
