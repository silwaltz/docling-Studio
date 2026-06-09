# Domain Layer (domain)

## Purpose

Pure domain logic: models, value objects, ports (abstract protocols), and domain utilities. Zero framework dependencies.

## Ownership

Backend team owns domain model design, business rules, and port definitions.

## Local Contracts

- **Pure Python**: No imports from `api`, `persistence`, `infra`, or any framework
- **Dataclasses**: Use `@dataclass` for entities and value objects
- **Ports**: Abstract protocols in `ports.py` define adapter contracts
- **Immutability**: Prefer immutable value objects where possible
- **Validation**: Domain-level validation in model constructors or factory methods
- **No I/O**: Domain layer must not perform I/O (file, network, database)

## Work Guidance

- **New model**: Add to `models.py` as dataclass
- **New value object**: Add to `value_objects.py`, make immutable if possible
- **New port**: Add protocol to `ports.py`, document expected behavior
- **Business rules**: Encode in domain methods, not in services
- **Testing**: Test domain logic in isolation, no mocks needed

## Verification

Domain tests in `tests/test_domain_*.py` must have zero external dependencies

## Child DOX Index

None (flat structure, all domain files in this directory)
