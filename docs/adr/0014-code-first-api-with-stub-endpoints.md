---
status: accepted
---

# The API contract is Pydantic schemas, and stub endpoints ship before implementations

Pulse is code-first, not spec-first. Pydantic schemas in `schemas.py` are the contract; FastAPI derives the OpenAPI document from them, and a build step generates TypeScript types from that document. Nobody hand-writes or hand-maintains an OpenAPI YAML file. As soon as a module's schemas merge, its endpoints exist behind a `@stub` decorator — returning fixture data, marked with an `X-Pulse-Stub: true` header — so frontend work against that module can start immediately rather than waiting on the real handler.

## Why

With four people on vertical, role-split ownership and a two-month timeline, the scheduling failure that actually happens is the frontend blocked on a backend implementation still in progress. Stub endpoints mean that never has to happen: the schema is the handoff point, not the finished handler, and the frontend builds and tests against fixture data that already has the right shape.

Code-first over spec-first is the same argument one layer down. A hand-maintained OpenAPI document is a second copy of the contract someone has to keep in sync with the actual Pydantic models by hand, and on a project this size it drifts from the code within a fortnight — not from carelessness, but because updating the spec is never what's blocking a PR, so it's always what gets skipped under pressure. Deriving the document from schemas FastAPI already validates against means there is nothing to keep in sync; it is either right or the application does not run.

## Consequences

The schema merge, not the implementation merge, becomes the real integration gate. Once a module's schemas land the frontend builds against them, which means schemas get reviewed harder than the handlers that will eventually fill them in — a contract change after the frontend is consuming it is expensive in a way that changing a function body is not.

A stub that survives to the demo is a lie: a screen that appears to work but returns the same fixture data regardless of what a Patient, Clinician or Provider Staff actually did. That is the failure mode stubs must not be allowed to hide, so a CI step prints the stub inventory on every run — visible in every PR rather than discovered the week of submission.

The generated TypeScript union this produces is also what ADR-0013's error-code contract relies on: one code-first pipeline serving two decisions.
