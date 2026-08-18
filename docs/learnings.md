# Learnings

Patterns used in Pulse, what they are, and why they are here. The point of this file is that anyone on the team can explain any part of the codebase, including the parts they did not type.

Appended as patterns land. Not written at the end.

---

## Repository pattern

**What:** All SQL lives in `repository.py`. Services call repository functions; they never build queries themselves.

**Why here:** It gives consent enforcement a single choke point. Because every entry read composes from one repository function (`accessible_entries`), the access rules can be applied in exactly one place instead of at every call site.

**Replaces:** Services calling the ORM directly, which spreads query construction — and therefore access-control decisions — across the whole codebase.

---

## Service layer

**What:** Business rules live in `service.py`. No SQL, no FastAPI imports, no HTTP concepts.

**Why here:** The interesting logic in Pulse — consent resolution, permission checks, merge semantics — is exactly the logic you want to test without starting a web server. Framework-free services make that possible.

**Replaces:** Business logic in route handlers, which is testable only through HTTP and gets duplicated the moment a second endpoint needs the same rule.

---

## Ports and adapters (hexagonal architecture)

**What:** `StorageProvider`, `NotificationProvider` and `IdentityProvider` are interfaces. Business logic depends on the interface; concrete implementations (local filesystem, Mailpit SMTP, email OTP) are injected.

**Why here:** Three parts of Pulse are explicitly planned to change — storage moves to object storage, notifications gain SMS, identity gains ABHA. The interface is what makes those swaps configuration rather than rewrites.

**Replaces:** Calling `open()` or `smtplib` from a service, which welds business logic to one deployment environment.

---

## Joined-table inheritance

**What:** One `medical_entry` table plus one table per entry kind, each keyed on the trunk's primary key. SQLAlchemy maps it with `polymorphic_on` / `polymorphic_identity`.

**Why here:** The five entry kinds share a handful of fields and diverge in about twenty-five. Typed columns per kind keep clinical data queryable and constrained — which is what makes both consent scoping and trend charts possible.

**Replaces:** One wide sparse table, or a JSONB blob. See ADR-0001 for why each loses.

**Worth knowing:** `selectin_polymorphic` loads a mixed page in one query per kind present, not one per row. The N+1 that everyone expects from this pattern does not occur.

---

## Opaque session tokens

**What:** A random token stored server-side in Redis, sent as an `HttpOnly` cookie. Not a JWT.

**Why here:** A JWT is valid until it expires, by design. Pulse promises that revoking consent takes effect immediately, which requires the server to have the final say on every request.

**Replaces:** JWT access tokens, which would need a server-side denylist to be revocable — at which point the statelessness that justified them is gone.

---

## Default-deny authorization

**What:** Every route declares a required permission or an explicit public marker. A test enumerates routes and fails CI on any that declares neither.

**Why here:** The realistic failure in a nine-module system is a *missing* permission check on an endpoint added under deadline pressure. Conventions do not catch that; a red build does.

**Replaces:** Checking permissions inside handlers, where forgetting produces a working endpoint that returns other people's medical records.

---

## Error codes over error messages

**What:** The API returns `{"error": {"code": "CONSENT_ALREADY_REVOKED", ...}}`. The frontend renders text from the code.

**Why here:** Four locales. A response body containing user-facing English is untranslatable without touching every endpoint.

**Replaces:** `{"detail": "This consent has already been revoked"}` — FastAPI's default, and the one-way door this project deliberately avoided.

---

## Cursor pagination

**What:** `?cursor=…&limit=…` returning `{items, nextCursor}`, rather than page numbers.

**Why here:** The timeline and audit log are append-heavy. Offset pagination on a table receiving new rows silently skips or duplicates records mid-scroll — corrupting exactly the two views that must be trustworthy.

**Replaces:** `?page=3&size=50`, which is friendlier right up until the data moves.
