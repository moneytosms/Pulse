# Architecture

How Pulse is built and why. Terms are defined in [`CONTEXT.md`](../CONTEXT.md); entity structure is in [`domain-model.md`](./domain-model.md); decisions with real trade-offs behind them are in [`adr/`](./adr/).

Supersedes `docs/archive/tech_stack_initial.md`.

**Status:** in progress. Filled in as the architecture tickets on [the map](https://github.com/moneytosms/Pulse/issues/1) resolve.

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

Four locales ship: English, Hindi, Tamil, Malayalam.

The API returns **machine-readable error codes** plus an English default message, never user-facing strings. This is the half that cannot be retrofitted: a raw `"Consent already revoked"` in a response body is untranslatable forever without touching every endpoint.

**The interface is localized; clinical data is not.** A Diagnosis recorded as "Type 2 diabetes mellitus" reads that way in every locale.

## Deployment

`docker compose up` brings the whole system up on any machine with Docker: `caddy`, `frontend`, `backend`, `postgres`, `redis`, `mailpit`.

Mail goes to Mailpit, which catches SMTP locally and serves a web inbox — nothing leaves the machine, no credentials in the repo, and the demo can show an email arriving. Real SMTP is an environment variable change, not a code change.
