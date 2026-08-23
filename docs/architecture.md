# Architecture

How Pulse is built and why. Terms are defined in [`CONTEXT.md`](../CONTEXT.md); entity structure is in [`domain-model.md`](./domain-model.md); decisions with real trade-offs behind them are in [`adr/`](./adr/).

Supersedes `docs/archive/tech_stack_initial.md`.

**Status:** settled. Every architecture ticket on the planning map resolved; this document is the result. It changes when the code teaches us something, not while questions are still open. Work is sliced across the team in [`delivery-plan.md`](./delivery-plan.md).

---

## Shape

A **modular monolith**. One FastAPI application, one PostgreSQL database, organised by business domain rather than technical layer.

```
auth · users · patients · providers · records · consent · audit · notifications · analytics · admin
```

Microservices would buy independent deployment and independent scaling. Pulse deploys as one Compose stack on a laptop and has no scaling requirement, so both benefits are unrealisable — while the costs (network calls between domains, distributed transactions, ten times the operational surface) are entirely real. The module boundaries are drawn as if extraction were coming, because that is what makes them useful today: they force explicit interfaces between domains.

**Modules communicate through service interfaces, never through each other's tables.** This is the rule that makes the boundaries mean anything, and it is the one that will be broken by accident — a direct join across domains is always the shortest path in the moment.

## Layers

```
routes.py      HTTP only — parse, validate, delegate. No business logic.
service.py     Business rules, permission checks, orchestration. No SQL, no framework.
repository.py  Persistence. All SQL lives here.
models.py      SQLAlchemy mappings.
schemas.py     Pydantic — the API contract.
```

The service layer must contain no framework-specific code. That is not aesthetics: it is what makes the business rules testable without spinning up HTTP, and it is where the interesting logic (consent, permissions, merge) lives.

## Adapters

Three things are external systems in disguise, and each sits behind an interface so it can be replaced without touching business logic:

| Adapter | Now | Later |
|---|---|---|
| `StorageProvider` | local filesystem on a mounted volume | S3, MinIO, Garage |
| `NotificationProvider` | in-app, plus SMTP to Mailpit | real SMTP, SMS, push |
| `IdentityProvider` | email verification and step-up | ABHA / government health ID |

`IdentityProvider` is deliberately a two-call interface — `start_verification` then `complete_verification` — rather than the single `verify()` originally sketched. Verification is two round trips, and a one-method interface would have left ABHA's flow nowhere to go.

## Request path

```
browser
  │
  ▼
Caddy ──── /api/*  ──▶  FastAPI
      └─── /*      ──▶  Next.js
```

One reverse proxy puts the frontend and the API **on the same origin**. This is not cosmetic: cookie authentication across origins means `SameSite=None`, CORS preflights, and a category of bug that appears only when the deployment differs from the developer's laptop. Six lines of Caddy config removes the category.

## Authentication

Opaque session tokens in Redis, delivered as an `HttpOnly` cookie — not JWTs. See [ADR-0003](./adr/0003-opaque-redis-sessions-not-jwt.md).

```
session:{sha256(token)}  →  { user_id, role, created_at, last_seen_at, ip, user_agent }
user_sessions:{user_id}  →  SET of session keys
```

The Redis key is the hash of the token, not the token, so a cache dump does not yield usable sessions. The per-user set makes "log out everywhere" and role-change invalidation one operation.

**Lifetimes:** 60 minutes idle (sliding), 12 hours absolute. The realistic threat in a clinical setting is an unattended workstation.

**Passwords:** Argon2id via `pwdlib[argon2]`, at argon2-cffi's default parameters (m=64 MiB, t=3, p=4 — above the OWASP minimum of m=19 MiB, t=2, p=1). Not passlib: its last release was 2020, despite being what every FastAPI tutorial still reaches for.

**Step-up verification** is required for granting consent, changing credentials, and administrator role changes — and deliberately *not* for revoking consent. Withdrawing access must be the frictionless direction; a patient who wants to cut off access should never be blocked waiting for an OTP.

## Authorization

Two mechanisms that must not be confused:

**Role permissions** answer *may a Clinician read records at all*. A FastAPI dependency, declared explicitly per route, default-deny, with a CI test that fails if any route declares neither a permission nor an explicit public marker. See [ADR-0004](./adr/0004-default-deny-route-authorization.md).

**Consent** answers *may this Clinician read this Patient's records*. That is a row-level query filter, not a boolean, and it lives in the repository layer. Passing the role check is necessary and never sufficient.

Records the caller has no consent for return **404, not 403**. A 403 confirms the record exists, which in a health system reveals that a person is a patient at all.

## Data

PostgreSQL for everything durable. Medical entries use joined-table inheritance — see [ADR-0001](./adr/0001-medical-entry-joined-table-inheritance.md) and the [domain model](./domain-model.md).

Redis holds sessions, rate-limit counters and short-lived verification challenges. Nothing else, ever — see [ADR-0005](./adr/0005-redis-is-never-a-source-of-truth.md).

Files live behind the storage adapter; the database holds only metadata, path and checksum.

## Internationalisation

Four locales ship: English, Hindi, Tamil, Malayalam. `next-intl` with path-prefixed routing (`/ta/records`), catalogs namespaced one file per feature per locale so four people editing translations do not conflict on every PR.

The middleware matcher **must exclude `/api`** — Caddy routes those to FastAPI on the same origin, and a locale middleware rewriting API paths breaks every request in a way that takes an hour to find.

Indian number and date conventions come from `Intl` natively — `Intl.NumberFormat('en-IN')` produces `12,34,567`, dates render day-first. No custom formatting code; writing some would produce a worse result than the platform already gives.

The API returns **machine-readable error codes** plus an English default message, never user-facing strings. This is the half that cannot be retrofitted: a raw `"Consent already revoked"` in a response body is untranslatable forever without touching every endpoint. Notifications are stored the same way — type plus parameters, rendered at read time.

Missing keys throw in development and CI, fall back to English in production. A silent fallback means a missing Tamil string is discovered by a reviewer who reads Tamil, live.

Fonts must carry Devanagari, Tamil and Malayalam. Most default UI stacks carry none of the three, and the failure is a silent fallback to whatever the OS has.

**The interface is localized; clinical data is not.** A Diagnosis recorded as "Type 2 diabetes mellitus" reads that way in every locale. Medication names, test names and note text are never translated — translating clinical content means generating medical claims the system cannot stand behind, and a mistranslated dosage is a safety issue, not a formatting one.

## Deployment

`docker compose up` brings the whole system up on any machine with Docker: `caddy`, `frontend`, `backend`, `postgres`, `redis`, `mailpit`.

Mail goes to Mailpit, which catches SMTP locally and serves a web inbox on `:8025` — nothing leaves the machine, no credentials in the repo, and the demo can show an email arriving beside the app. Real SMTP is an environment variable change, not a code change.

Email is dispatched via FastAPI `BackgroundTasks` after the response returns. There is no task queue and none is being added: a broker plus a worker container is real infrastructure for a handful of messages. The trade-off is explicit — a failed send is logged and lost, which is acceptable because the in-app notification is written transactionally and is the system of record.

`git clone && docker compose up` must produce a working, seeded system. That is the acceptance test for the scaffold.

## Testing

Integration tests against a real PostgreSQL container are the spine — the project's risk is concentrated in *did the consent filter actually apply to that query*, and a mocked-database test tests the mock. Unit tests are reserved for genuinely branchy logic: permission resolution, duplicate scoring, consent expiry.

The negative tests are the ones that matter: revoked consent returns nothing, expired consent returns nothing, consent scoped to lab reports does not leak clinical notes, an administrator gets nothing, an unauthorised clinician gets 404 rather than 403. A positive test passes just as happily when the filter is missing entirely.

CI gates every PR — `ruff`, `mypy`, `pytest` for the backend; `eslint`, `tsc --noEmit`, `next build` for the frontend; plus the route-coverage test, the entry-query lint and the cross-module import lint. No pre-commit hooks: they get bypassed and generate noise commits, and CI cannot be argued with.
