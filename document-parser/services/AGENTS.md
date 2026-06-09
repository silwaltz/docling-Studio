# Services Layer (services)

## Purpose

Use case orchestration. Coordinates domain logic, repositories, and infrastructure adapters to fulfill business operations.

## Ownership

Backend team owns service design, orchestration logic, and transaction boundaries.

## Local Contracts

- **Orchestration**: Services coordinate calls to repos, converters, chunkers
- **Transaction boundaries**: Services define atomic operations
- **Error handling**: Catch adapter errors, translate to domain exceptions
- **Async**: All service methods are async
- **Dependencies**: Injected via constructor (repos, adapters, config)
- **No HTTP**: Services have no knowledge of HTTP or API layer

## Work Guidance

- **New service**: Create new file, inject dependencies via `__init__`
- **Use cases**: One public method per use case
- **Atomicity**: Document transaction boundaries in docstrings
- **Logging**: Log use case start/end and errors
- **Config**: Accept config objects, not individual env vars
- **Testing**: Test with mocked repos and adapters

## Verification

Service tests in `tests/test_service_*.py` use mocked dependencies

## Child DOX Index

None (flat structure, all service files in this directory)
