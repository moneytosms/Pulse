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

---

## Request-id middleware

**What:** A random identifier is generated at the edge for every request, attached to the error envelope's `requestId` field, set on the `X-Request-Id` response header, included in every log line for that request, and stored on the `request_id` column of any Audit Event the request writes.

**Why here:** The actual support question on a nine-module system is "it failed at 3pm", with no stack trace and often no memory of which screen. The request id is the only thread that ties that sentence to a log line and, when clinical data was touched, to the specific Audit Event. It is generated once, at the edge, so every layer downstream just has to pass it along rather than derive it.

**Replaces:** Correlating by timestamp and username, which breaks the moment two requests land in the same second.

---

## `@stub` endpoints and the CI stub inventory

**What:** An endpoint decorated `@stub` returns fixture data shaped like its real response schema, sets `X-Pulse-Stub: true`, and registers itself. CI prints the inventory of remaining stubs on every run. See ADR-0014.

**Why here:** Backend and frontend are owned by different people, and the scheduling failure that actually happens on this team is the frontend blocked waiting on a backend handler. Once a module's schemas merge, the frontend can build against the real shape immediately — the stub, not the finished implementation, is the handoff point.

**Worth knowing:** The inventory is not a TODO list someone has to remember to check. It prints on every CI run, so a stub count that should be falling and isn't is visible in every PR, not discovered the week of submission.

---

## camelCase at the boundary, snake_case inside

**What:** One shared `PulseSchema` base sets `alias_generator=to_camel` plus `validate_by_name=True` and `validate_by_alias=True`. Python stays snake_case everywhere; JSON is camelCase everywhere.

**Why here:** Four people, two languages' worth of convention, and neither side should have to write the other's style. Converting at a single base model means the boundary is crossed in exactly one place — nobody hand-renames a field per endpoint, and there is one spot to check when the conversion misbehaves.

**Replaces:** Field-by-field aliasing per schema, which is what happens without a shared base, and camelCase leaking into Python or snake_case leaking into JSON, which is what happens without any conversion at all.

**Worth knowing:** `populate_by_name` is deprecated as of Pydantic 2.11 in favour of the two separate flags above — every tutorial and most Stack Overflow answers still show the old one.

---

## Two database roles

**What:** The application connects as a database role holding only `INSERT` and `SELECT` on `audit_event`. No `UPDATE`, no `DELETE` — those require a separate migration-owner role. See ADR-0008.

**Why here:** Pulse's compliance story rests on the audit log being genuinely immutable, not merely treated that way by convention. "The service layer never updates that table" is an intention, and intentions survive exactly until someone writes a cleanup script under deadline pressure or a bug does it by accident.

**Replaces:** Application-level discipline — a code-review rule against writing `UPDATE`/`DELETE` against `audit_event` — which cannot be proven to an examiner. A grant is a fact about the database itself, checkable with a permissions query, independent of what the application code happens to do.

---

## Enforcement tests as lints

**What:** Three CI checks: route permission coverage (every route declares a permission or an explicit public marker), a lint against raw `select(MedicalEntry)` anywhere outside `accessible_entries`, and a cross-module import lint (no domain reaching into another's tables).

**Why here:** All three catch an absence — a missing permission check, a query that bypassed the consent filter, a shortcut join across a module boundary — and human review is unreliable at noticing something that isn't there. A red build is not.

**Worth knowing:** These were introduced against three endpoints, not sixty. Writing the lint against the whole codebase at once produces a wall of failures and an irresistible urge to mark everything exempt, which defeats the point before it starts.

---

## Integration tests against a real PostgreSQL container

**What:** The test spine runs against a real, containerised PostgreSQL instance. Unit tests are reserved for branchy logic — permission resolution, duplicate scoring, consent expiry — that doesn't need a database to exercise.

**Why here:** Pulse's risk is concentrated in one question: did the consent filter actually apply to that query. A test against a mocked database only tests that the mock was called correctly — it cannot fail the way a real missing `WHERE` clause fails.

**Worth knowing:** The negative tests are the ones that matter — revoked consent returns nothing, an unauthorised clinician gets 404. A positive test ("consented clinician sees the entry") passes just as happily when the filter is missing entirely, because the entry would come back either way.

---

## Notifications stored as type plus params

**What:** `notification` stores `type` and a `params` JSONB blob, never rendered text. The body is rendered at read time through the locale catalogs.

**Why here:** Four locales ship, and a notification is typically read weeks after it's written — by which point "render once, in whatever locale the server had" has already picked the wrong language for at least three of them. Storing type and params defers rendering to whenever and wherever it's actually read.

**Replaces:** Storing the rendered English string, which is what every tutorial's notification model does and which is untranslatable after the fact.

**Worth knowing:** `params` carries identifiers and non-clinical values only — the same rule as Audit Event metadata, for the same reason: a notification is a copy of information that sits outside the consent filter, so clinical content inside it would be a second, unguarded copy of the record.

---

## Email through `BackgroundTasks`, no queue

**What:** Email is dispatched via FastAPI's `BackgroundTasks` after the response returns, rather than through a message broker and worker process.

**Why here:** A broker plus a worker container is real infrastructure — another service to run, monitor and keep alive in the Compose stack — for a handful of transactional emails a day. Pulse doesn't have the message volume or the delivery guarantees that would justify it.

**Worth knowing:** The trade-off is real, not hidden: a failed send is logged and lost, nothing retries it. That is acceptable only because the in-app notification is written transactionally before the email is attempted, and it — not the email — is the system of record. If email delivery ever needs to be guaranteed, that's the signal a queue has become worth its cost.

---

## Path-prefixed locale routing with `/api` excluded from the matcher

**What:** `next-intl` handles locale routing with path prefixes (`/ta/records`, `/en/patients`), and its middleware matcher is configured to skip anything under `/api`.

**Why here:** Caddy puts Next.js and FastAPI on one origin (ADR-0012) so cookie auth never crosses origins — which means every backend request also passes through the path a naive `next-intl` matcher would try to rewrite. A locale middleware that prefixes or rewrites `/api/v1/patients` breaks every single API call, and because it's a middleware concern rather than a route concern, the failure shows up as a confusing 404 or a mis-routed request that takes about an hour to trace back to i18n config nobody was looking at.

**Replaces:** The default `next-intl` matcher, which assumes the whole origin is pages to localize — true for most Next.js apps and false the moment the API shares the origin.

---

## Corrections by supersession

**What:** A corrected Medical Entry is never updated or deleted. A new Entry is inserted with the corrected data, and the original gets `superseded_by_id` set to point at it. The timeline filters `superseded_by_id IS NULL`; the full chain stays queryable behind that filter.

**Why here:** An audit story that permits silent `UPDATE`s on clinical data undermines the whole point of keeping an audit log — the log would say a diagnosis was viewed, but not that the diagnosis itself quietly changed underneath it. "What did this say before it was corrected?" is a question a clinician can legitimately ask, and it needs an answer, not a shrug.

**Replaces:** In-place `UPDATE`, which is what a naive edit form would do and which destroys the previous value the moment the correction is saved.

---

## 404 where you would expect 403

**What:** When a Clinician's Role permits reading clinical data but no Consent covers the Patient in question, the API returns **404 Not Found**, not 403 Forbidden. 403 is reserved for the Role failing outright.

**Why here:** A 403 on `/api/v1/patients/{id}/entries` is an answer: it says the record exists. In a health system that discloses that a named person is a patient at all — which may be the single most sensitive bit in the whole database, before anyone reads a diagnosis. The status code itself is a side channel, and 404 closes it.

**Replaces:** The textbook mapping of "authenticated but not permitted → 403", which is right in most systems and wrong in this one.

**Worth knowing:** This has to be consistent everywhere, including on document downloads and analytics endpoints. One endpoint that returns 403 re-opens the channel for every patient in the system.

---

## Duplicate detection: block before you score (P4.1)

**What:** `blocked_candidates` narrows every Patient pair to same-birth-year, same-phone, or a trigram index hit on `full_name` *before* `score_pair` runs. Name similarity itself is a token-sorted trigram Jaccard, not Soundex/Metaphone, and scoring is a weighted blend (name 0.5, DOB 0.3, phone 0.2). See ADR-0011, `.claude/rules/database.md`.

**Why here:** Unblocked pairwise scoring is O(n²) and gets worse with every seeded or real Patient added — it doesn't fail loudly, it just gets slower until someone notices duplicate review is timing out. Token-sorting the name before trigram comparison matters specifically for this demographic: Indian naming order varies by region ("Menon Ramesh" vs "Ramesh Menon"), and Soundex/Metaphone encode English phonetics, so they misscore romanised Indian names both ways — false negatives on real duplicates and false positives on unrelated names that happen to sound alike in English.

**Worth knowing:** Precision/recall is measured, not assumed — the test suite runs scoring against the seed's own planted pairs (`seed/data/identity/planted_pairs.csv`, ADR-0015): 3 planted duplicates flagged, 2 planted near-misses correctly not flagged. A negative test also asserts two genuinely unrelated patients produce zero candidates.

---

## Merge/reversal/review-decisions are gated to a human Administrator at the service layer, not just the UI

**What:** `merge_patients`, `reverse_merge` and `mark_not_duplicate` (`users/service.py`) reject any actor whose role isn't `ADMINISTRATOR`, independent of whatever called them. `lint_actor_first.py` was extended to scan the admin module alongside `records/`.

**Why here:** ADR-0011 says merges are human-initiated; the risk that decision guards against is a future batch job or scheduled task calling the merge function directly, bypassing whatever admin-only route check exists at the HTTP layer. Putting the check in the service function itself means there is no code path — present or future — that can auto-merge two Patients' histories, which is this system's worst possible failure mode.

**Replaces:** Gating only at the route (`requires(Permission.ADMIN_...)`), which protects the HTTP surface but not a same-process caller that skips routing entirely.

---

## Analytics abnormality flags compare against each row's own reference range (P4.3)

**What:** `_is_abnormal` (`analytics/service.py`) flags a lab result against *that row's own* `reference_low`/`reference_high` columns, never a hardcoded clinical range.

**Why here:** ADR-0009 already committed analytics to being computed on read, through `accessible_entries`, with no stored insight table. P4.3 extends that same principle down to the comparison itself: a hardcoded "normal range" is a second, unauthoritative copy of clinical knowledge baked into application code, and it would silently disagree with whatever range the lab that produced the result actually used. Reading the bounds off the row that was seeded means the flag is only ever as wrong as the source data, never wrong because someone typed a textbook range into a Python file.

**Worth knowing:** This is why `database.md` requires `value_numeric`/`value_text` plus two numeric reference-range columns on every lab result — out-of-range flagging has to be a comparison, never a string parse, and it has to be per-row, never per-test-name.

---

## The admin duplicate-review count is a deliberate, narrow bypass of `accessible_entries`

**What:** `records.service.entry_count_for_patient` and `records.repository.count_entries_for_patient` return a row count for the admin duplicate-review queue without going through `accessible_entries` at all. The repository function still takes an `actor` parameter (the actor-first lint requires it), but doesn't filter on it — the caller (`entry_count_for_patient`) is what actually enforces `Role.ADMINISTRATOR`-only before the count ever runs, and the docstring on both functions says explicitly that this must never be reused as a general-purpose count.

**Why here:** `accessible_entries` returns nothing at all for an Administrator actor, by design (ADR-0007: Administrators read no clinical data, ever). But ADR-0011's merge UI needs *some* signal for "which of these two candidate Patients has more history" to suggest a sensible merge winner — and a bare integer count carries no clinical content, which is exactly the line ADR-0007 draws. So this one query had to be exempted from the standard access path on purpose, rather than either (a) quietly threading an Administrator through `accessible_entries` and weakening what that function guarantees everywhere else, or (b) leaving the merge screen with no way to distinguish the two candidates at all.

**Worth knowing:** This is a named, single-purpose exception, not a precedent. See `.claude/errors.md`'s 2026-09-12 entry for the related near-miss on the same feature (identity data-quality flags read Patient fields with no actor gate at all, caught by security review, not by CI) — the fix there was the general rule this carve-out deliberately narrows around: any function reading personal (not just clinical) data takes an actor and gates on it, and the negative case gets a test. `entry_count_for_patient`'s own negative test (non-Administrator gets 403) is that test for this function.

---

## Frontend rebuilt on shadcn/ui components (P4.4, PR #59)

**What:** The hand-rolled primitives in `src/components/ui/` (`Button`, `Card`, `Callout`, `FormField`, `NavLink`, ...) and `src/styles/tokens.css` were replaced with shadcn/ui components generated into the same directory, themed from `src/app/globals.css`. Dark mode is class-based via `next-themes` (`defaultTheme="light"`, header toggle), not a media query. Project-specific tokens (`--critical`, `--critical-surface`, `--critical-border`) sit alongside shadcn's own.

**Why here:** Phase 4 added data-dense screens (analytics, admin, duplicate review) that needed tables, charts, sheets and form fields the original kit did not have. shadcn components are copied into the repo, not imported from a package, so they are still "wrapped once, in the shared directory" (`frontend.md`) and can be edited.

**Worth knowing:** shadcn's `destructive` colour is a generic error red, not a clinical-severity colour, and its `Badge` variant measured **3.97:1** in light mode, below WCAG AA's 4.5:1 for 12px text. Clinical flags (abnormal lab results, critical entries) use the `--critical` tokens (5.87:1 light, 8.42:1 dark). The patient-side abnormal marker drifted to `variant="destructive"` during the rebuild and was moved back in P4.5. Check contrast by computing ratios from resolved colours in the running app, not by eye.
