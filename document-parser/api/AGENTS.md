# API Layer (api)

## Purpose

FastAPI HTTP routers and Pydantic schemas. Translates HTTP requests to service calls and domain responses to JSON.

## Ownership

Backend team owns route definitions, request/response schemas, and HTTP error handling.

## Local Contracts

- **Serialization**: camelCase JSON via Pydantic `alias_generator`
- **Validation**: Pydantic models for all request/response bodies
- **Error handling**: Map domain exceptions to appropriate HTTP status codes
- **Route naming**: RESTful conventions, DDD-granular (one route ≈ one domain op)
- **Dependencies**: Use FastAPI dependency injection for repos and services
- **CORS**: Configured in `main.py`, not per-route

## Work Guidance

- **New route**: Add to appropriate router file, update OpenAPI tags
- **Schema**: Define in `schemas.py`, use `Field()` for validation and docs
- **Status codes**: 200 OK, 201 Created, 204 No Content, 400 Bad Request, 404 Not Found, 422 Validation Error, 500 Internal Server Error
- **Async**: All route handlers must be async
- **Documentation**: Use docstrings and OpenAPI metadata
- **Testing**: Test via pytest with TestClient, not direct function calls

## Verification

Routes tested via `tests/test_api_*.py`

## Child DOX Index

None (flat structure, all routers in this directory)
