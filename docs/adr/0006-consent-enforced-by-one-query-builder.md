---
status: accepted
---

# Consent is enforced by a single query builder, not by scattered checks

Every read of Medical Entries composes from one function — `accessible_entries(actor, patient_id)` — which applies the access rules as SQL. No repository method returning entries takes less than an `actor`. A CI check fails if `select(MedicalEntry)` appears anywhere outside that function.

## Why

Consent is a row-level question — *may this Clinician read this Patient's entries, of these types, in this date range, right now* — so it cannot be a boolean check before a query. It has to be part of the query.

Given that, the only real design question is how many places can construct such a query. The answer must be one. A permission check that a developer can forget to write is a permission check that will be forgotten, and the consequence here is silently returning someone's medical history.

Postgres row-level security was the alternative. Rejected: it needs per-request `SET LOCAL` session variables, which interacts badly with connection pooling, and it hides the project's most important logic somewhere none of the developers will look while debugging.

## Consequences

Enforcement is a lint plus negative integration tests, not a formal guarantee. That is an honest limitation — but the failure mode it catches (someone writing a fresh unfiltered query in a hurry) is the one that actually occurs.

No permission decision may be cached anywhere, including Redis. Caching a decision for even sixty seconds makes "revocation is immediate" false.

Anything derived from entries — analytics especially — must compose from the same builder. Derived data is the easiest way to leak the data it was derived from.
