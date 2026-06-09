# Persistence Layer (persistence)

## Purpose

SQLite data access via aiosqlite. Implements repository pattern for documents, analyses, chunks, stores, and edits.

## Ownership

Backend team owns schema design, migrations, and repository implementations.

## Local Contracts

- **Database**: SQLite via aiosqlite, schema in `database.py`
- **Repositories**: One repo per aggregate root
- **Transactions**: Use `async with get_connection()` for atomic operations
- **Schema init**: `init_db()` creates tables if not exist
- **Migrations**: Manual SQL migrations for schema changes
- **Error handling**: Raise domain exceptions, not SQLite errors

## Work Guidance

- **New table**: Add CREATE TABLE in `database.py:init_db()`
- **New repo**: Create `*_repo.py`, implement CRUD methods
- **Queries**: Use parameterized queries, never string interpolation
- **Indexes**: Add indexes for frequently queried columns
- **Testing**: Use in-memory SQLite (`:memory:`) for tests
- **Cleanup**: Close connections properly, use context managers

## Verification

Persistence tests in `tests/test_persistence_*.py` use in-memory database

## Child DOX Index

None (flat structure, all repository files in this directory)
