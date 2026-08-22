# Backend Rules

FastAPI + Python. Applies to `backend/`.

## Layering

- `routes.py` is HTTP only — parse, validate, delegate. No business logic.
- `service.py` holds business rules. **No SQL, no FastAPI imports, no HTTP concepts.** This is what makes consent, permission and merge logic testable without starting a web server.
- `repository.py` holds all SQL. Services call repository functions; they never build queries.
- Modules communicate through service interfaces, never through each other's tables. A cross-domain join is always the shortest path in the moment — that is exactly why it is a rule. CI lints cross-module imports.

## Schemas and the wire

- Every schema inherits `PulseSchema` — `alias_generator=to_camel`, `validate_by_name`, `validate_by_alias`. JSON is camelCase, Python stays snake_case.
- `populate_by_name` is deprecated in Pydantic 2.11. Use `validate_by_name` / `validate_by_alias`; every tutorial still shows the old one.
- Error responses are always the coded envelope — `{"error": {"code", "message", "details", "requestId"}}`. FastAPI's default `{"detail": ...}` is replaced globally, including for `RequestValidationError`.
- Error codes are `SCREAMING_SNAKE_CASE`, live in one Python enum, and are **stable forever, never reworded**. The frontend renders from `code`, never from `message`.
- Cursor pagination everywhere: `?cursor=&limit=` returning `{items, nextCursor}`. Never offset pagination — the timeline and audit log are append-heavy and offset silently skips rows mid-scroll.

## Contracts before implementations

- Schemas and repository signatures merge first, stubs second, implementations third. A screen blocked on a finished backend service means a stub was skipped.
- `@stub` endpoints return fixture data matching the real schema. CI prints the stub inventory; a stub that survives to the demo is a lie.

## Adapters

- `StorageProvider`, `NotificationProvider`, `IdentityProvider` are interfaces. Never call `open()` or `smtplib` from a service.
- `IdentityProvider` is two calls — `start_verification` then `complete_verification` — because verification is two round trips and ABHA's flow needs somewhere to go.

## Auth

- Sessions are opaque tokens in Redis keyed by `sha256(token)`, delivered as an `HttpOnly` `SameSite=Lax` cookie. Not JWTs (ADR-0003).
- Argon2id via `pwdlib[argon2]` at library defaults. Not passlib — its last release was 2020.
- Step-up verification is required for granting consent, changing credentials and administrator role changes — and deliberately **not** for revoking consent. Withdrawing access must be the frictionless direction.

## Tests

- Integration tests against a real PostgreSQL container are the spine. A mocked-database test tests the mock, and this project's risk is entirely "did the filter actually apply to that query".
- Unit tests are for genuinely branchy logic only: permission resolution, duplicate scoring, consent expiry.
- Write the negative test first. A positive test passes just as happily when the filter is missing entirely.
