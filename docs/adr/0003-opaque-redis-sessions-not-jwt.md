---
status: accepted
---

# Sessions are opaque tokens in Redis, not JWTs

Authentication uses a random opaque token stored server-side in Redis, delivered as an `HttpOnly` cookie. We are not using JWTs.

This is recorded because JWT is the default assumption for a FastAPI project and someone will propose it again.

## Why

Pulse's central promise is that a Patient can revoke a Clinician's access and it stops *immediately*. A JWT is a bearer credential that is valid until it expires, by design — the server has no say once it is issued. Recovering immediate revocation means adding a server-side denylist checked on every request, at which point you have server-side session state anyway, plus a token format that is harder to reason about.

The usual argument for JWT is stateless horizontal scaling. Pulse deploys as a Docker Compose stack on a laptop. That benefit is never collected, and it was being traded against the one property the project is actually judged on.

Opaque sessions are also simpler to explain, which matters for a project whose authors must be able to defend every part of it.

## Consequences

Redis becomes load-bearing for authentication: if it is wiped, every user is logged out. That is the acceptable failure mode, and it is the boundary recorded in ADR-0005 — nothing durable lives in Redis, so "everyone logs in again" is the worst case.

The token is stored in Redis under the SHA-256 of its value rather than the value itself, so a cache dump does not yield usable sessions.
