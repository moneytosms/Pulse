# Delivery Plan

Who builds what, in what order, and where the waiting happens.

Architecture is settled — see [`architecture.md`](./architecture.md), [`domain-model.md`](./domain-model.md), [`api-conventions.md`](./api-conventions.md) and [`adr/`](./adr/). This document is the other half: turning those decisions into four people's work without them blocking each other.

Tracked on [the build plan](https://github.com/moneytosms/Pulse/issues/17): one slice ticket per person — [#18 database](https://github.com/moneytosms/Pulse/issues/18) · [#19 backend](https://github.com/moneytosms/Pulse/issues/19) · [#20 frontend](https://github.com/moneytosms/Pulse/issues/20) · [#21 platform](https://github.com/moneytosms/Pulse/issues/21). This file is the reasoning behind the slices.

---

## Team and ownership

Ownership is **horizontal by layer**, not vertical by feature. Four people, three layers, one integrator.

| Person | Owns | Concretely |
|---|---|---|
| **Shivansh** | Database | SQLAlchemy models, Alembic migrations, the repository layer, indexes, `accessible_entries`, seed pipeline, duplicate scoring |
| **Akshay** | Backend | FastAPI app, `core/`, services, routes, Pydantic schemas, auth and sessions, the three adapters, background tasks |
| **Bharadwaj** | Frontend | Next.js app, design system, i18n, all four portals, Playwright |
| **Srimoney** | Platform + integration | Compose, Caddy, CI, the three enforcement tests, review of every PR, integration, deployment, demo. Floats into any layer that is behind. |

The earlier plan was vertical ownership — each person owning a module front-to-back. That changed because the team's actual strengths are layer-shaped. The trade-off is real and worth naming: horizontal slices mean **no feature is finished by one person**, so a feature is only done when three people's work meets. That makes the contracts between layers the most important artifact in the project, which is what the next section is about.

---

## The rule that makes this parallel

> **Contracts merge first. Implementations merge second.**

Every module passes three gates, in order. Each gate unblocks somebody else, and the gate is *merged code*, not a conversation.

| Gate | What merges | Who is unblocked |
|---|---|---|
| **G1 — Contract** | Pydantic schemas (Akshay) + repository function signatures, bodies raising `NotImplementedError` (Shivansh) | Everyone. The shape is now fixed. |
| **G2 — Stub** | `@stub` endpoint returning fixture data matching the schema (Akshay) | Bharadwaj builds the real screen against a real HTTP response. |
| **G3 — Implementation** | Service + repository filled in, integration tests green (Akshay + Shivansh) | The demo. |

This is what [ADR-0014](./adr/0014-code-first-api-with-stub-endpoints.md) buys, and it is the whole reason the frontend can run a phase ahead of the backend rather than a phase behind it.

**Three standing rules that follow from it:**

1. **Bharadwaj waits on schemas, never on implementations.** If a screen is blocked on a backend service being finished, the stub was skipped and that is the bug.
2. **Akshay waits on repository signatures, never on repository implementations.** A service can be written and unit-tested against a repository function that raises.
3. **Shivansh waits on nobody after the first migration lands.** Schema shape questions go to Akshay, but the migration and model work is upstream of everything.

The one unavoidable serial dependency is the review queue. Srimoney reviews every PR, so **PRs are one ticket each and stay small**; a 900-line PR is a day of latency for whoever needs it merged.

---

## Phase 0 — bootstrap (first 2 days)

Everything else depends on the directory tree existing. So it lands first, empty, in hours — not days.

**Srimoney, hour zero:** the repo skeleton exactly as specified in the scaffold ticket — `backend/app/{core,db,modules,adapters}`, every module directory carrying empty `routes.py` / `service.py` / `repository.py` / `models.py` / `schemas.py`, `frontend/src`, `seed/`, `compose.yaml`, `Caddyfile`, CI workflow. No logic. One commit. This is time-boxed to 24 hours because three people are idle behind it.

Once that tree exists, the four of them work in **disjoint directories** and Phase 0 is fully parallel:

| Person | Phase 0 |
|---|---|
| Srimoney | Skeleton, Compose with all six services, Caddy same-origin routing, CI running green on an empty repo, branch protection on `main`, issue labels |
| Akshay | `core/`: `PulseSchema` base with `to_camel` aliasing, error envelope, error-code enum, global exception handler (including `RequestValidationError`), request-id middleware, cursor pagination helper, `@stub` decorator |
| Shivansh | `db/`: async session, declarative base, Alembic init, **first migration** — two database roles, audit `GRANT` restriction, `pg_trgm` extension |
| Bharadwaj | Next app skeleton, `next-intl` routing with the middleware matcher **excluding `/api`**, design-token decision (typography + palette), component conventions |

**Exit:** `docker compose up` starts six containers and CI is green on an empty repo.

---

## Phase 1 — skeleton

*Demoable: a user registers, verifies by email in Mailpit, logs in, sees a seeded Patient's profile, switches to Hindi. CI blocks a route that declares no permission.*

**Shivansh** — `User`, `Patient`, `Provider`, `ProviderStaff` models and migrations; users and patients repositories; seed pipeline part one (pinned Synthea invocation, deterministic Indian overlay, dataset committed); the loader that seeds on first `compose up`.

**Akshay** — auth module end to end: registration, email verification through `IdentityProvider.start_verification` / `complete_verification`, login, logout, Argon2id via `pwdlib`, session middleware, Redis client, sliding 60-minute / absolute 12-hour lifetimes, `user_sessions:{user_id}` for log-out-everywhere. The `requires(Permission)` dependency. Step-up verification. Users module vertically complete. G1+G2 for records and consent so Bharadwaj is never idle.

**Bharadwaj** — design system landed for real: tokens, typography, the wrapped Radix primitives, and where a shared component lives. Auth screens, locale switcher, patient profile against stubs. English plus Hindi wired properly — two locales prove the pipeline; four prove nothing extra and cost three times the catalog churn this early.

**Srimoney** — the three enforcement tests, landed now while there are three endpoints and not sixty: route-coverage (default-deny, [ADR-0004](./adr/0004-default-deny-route-authorization.md)), the `select(MedicalEntry)` lint ([ADR-0006](./adr/0006-consent-enforced-by-one-query-builder.md)), and the cross-module import lint. The "authenticate as role X" test fixture. Mailpit wired into the demo. README quickstart. Every PR reviewed.

**Gate to Phase 2:** `git clone && docker compose up` on a machine that has never seen the project produces a working, seeded, logged-in-able system. That is the acceptance test, and it is checked on someone else's laptop, not the author's.

---

## Phase 2 — records spine

*Demoable: Provider Staff uploads a lab report against a Patient; the Patient sees it on their timeline, in the order they lived it.*

**Shivansh** — `medical_entry` trunk plus five subtype tables, joined-table inheritance mapped with `polymorphic_on` / `polymorphic_identity`; the five indexes; `selectin_polymorphic` on timeline reads; `medical_document` metadata; cursor-paginated timeline query filtering `superseded_by_id IS NULL`; seed loads entries with real SNOMED/LOINC/RxNorm codes.

**Akshay** — records module services and routes; provider upload; MIME allowlist with server-side sniffing and size limits; `StorageProvider` adapter over the local filesystem; document serve and download; the correction path that inserts a new Entry and stamps `superseded_by_id` rather than updating; providers module.

**Bharadwaj** — the patient timeline. This is the centrepiece and the hardest screen in the project: dense, chronological, five mixed entry types, mobile-first on a mid-range Android. Entry detail per subtype, document viewer, provider upload with progress and field-level validation errors. Tamil and Malayalam catalog *structure* lands here — empty keys that throw in CI — so P4 is a translation job and not a plumbing job.

**Srimoney** — uploads volume and Caddy body limits, upload integration harness, demo-spine smoke test in CI, review, integration.

**Gate to Phase 3:** the first half of the demo spine — upload to timeline — works on a fresh clone.

---

## Phase 3 — consent, audit, notifications

*The graded half. It sits in the middle of the schedule deliberately: this is the part that must not be what gets cut.*

**Shivansh** — `consent` and `access_permission` tables; the `audit_event` table with its append-only `GRANT`; the `(patient_id, occurred_at)` audit index that serves "who accessed my records"; notification tables. And the crown jewel: **`accessible_entries(actor, patient_id)`** — the five access rules as one composable query filter.

**Akshay** — consent service: grant behind step-up, revoke without step-up (withdrawing access is the frictionless direction, by design), mandatory expiry defaulting to 30 days, entry-type and date scoping. Break-glass: written justification, 60 minutes, `CRITICAL` audit event, Patient notified immediately. Explicit audit emission on every service path including reads. The Patient's filtered audit projection. Notification service with type+params storage, per-type per-channel preferences, the read-computed daily digest, `NotificationProvider` over Mailpit through `BackgroundTasks`.

**Bharadwaj** — consent grant and revoke flows, where revoke is deliberately the shorter path; scope selection (entry types plus date window, never per-entry ticking); the "who accessed my records" view; notification centre and preferences with mandatory events absent rather than shown as locked toggles; the break-glass banner; the clinician record view including its consent-denied state.

**Srimoney** — **the adversarial suite**, and it is his because the author of a filter is the worst person to test it:

- revoked Consent returns nothing — including for a Clinician mid-session
- expired Consent returns nothing
- Consent scoped to lab reports does not leak clinical notes
- an Administrator gets nothing, on every clinical endpoint
- an unauthorised Clinician gets **404, not 403**
- the audit `GRANT` actually rejects `UPDATE` and `DELETE` from the application role
- no permission decision is cached anywhere

A positive test passes just as happily when the filter was never applied. These are the tests the grade rests on.

**Gate to Phase 4:** the entire demo spine works — sign up, upload, timeline, grant, clinician reads, patient sees the access, patient revokes, clinician is locked out immediately — and every negative test above is green. **Nothing from Phase 4 starts until this gate passes.**

---

## Phase 4 — analytics, admin, deduplication, locales, polish

**Shivansh** — `pg_trgm` GIN indexes; candidate blocking before scoring; trigram similarity on token-sorted names with the DOB and phone components; merge with tombstone and reversal; a precision/recall number against the planted duplicates *and* the planted near-misses; the analytics queries, every one of them composed from `accessible_entries`.

**Akshay** — analytics computed on read, abnormality flagged against each row's own `reference_low` / `reference_high`; admin module that touches no clinical data; duplicate review service; human-only reversible merge; data-quality flags.

**Bharadwaj** — analytics charts, admin dashboard, duplicate review UI showing identity fields and entry counts but never clinical contents, Hindi/Tamil/Malayalam catalogs filled, accessibility and contrast pass, Playwright over the demo journey.

**Srimoney** — locale review, one native speaker per language against a written checklist; Playwright in CI; docs consolidation; the demo script and two rehearsals; submission packaging; and the deployment call — laptop Compose is the assumed answer, and an always-on instance only happens if integration proves it earns its keep.

---

## What waits on what

```
Phase 0   Srimoney skeleton ──┬──▶ Akshay core
          (24h, blocking)     ├──▶ Shivansh first migration
                              └──▶ Bharadwaj app + design tokens

Per module, every phase:

  Shivansh repo signature ─┐
                           ├──▶ G1 contract ──▶ G2 stub ──▶ Bharadwaj screen
  Akshay schemas ──────────┘                        │
                                                    └──▶ G3 implementation ──▶ demo

Phase gates (hard):

  P1 ──▶ P2   fresh clone boots, seeded, login works, enforcement tests live
  P2 ──▶ P3   upload lands on the timeline
  P3 ──▶ P4   full demo spine + every negative test green
```

**Genuinely parallel, all phases:** Bharadwaj's screens against stubs · Shivansh's migrations · Akshay's services against raising repositories · Srimoney's CI and tests.

**Genuinely serial, and therefore watched:** the Phase 0 skeleton · the review queue · `accessible_entries` before anything in Phase 3 that reads clinical data · design tokens before any second screen exists.

---

## Shared-ownership calls

Three pieces of work do not belong cleanly to one layer. Leaving that implicit is how they end up owned by nobody.

**`accessible_entries`** — Shivansh writes the SQL, Akshay supplies actor and permission resolution, Srimoney writes the tests that attack it. Three people, one function, on purpose: it is the single point where the project's central promise is either kept or quietly broken.

**Audit emission** — Akshay emits, Shivansh guarantees the table cannot be rewritten, Srimoney tests coverage of the read paths. Reads are the events that matter and reads write nothing, so no hook can catch them ([ADR-0008](./adr/0008-audit-log-is-append-only-by-grant.md)).

**The error-code enum** — Akshay owns the Python enum, Bharadwaj consumes the generated TypeScript union, neither hand-maintains a list. A code, once merged, is never reworded ([ADR-0013](./adr/0013-error-codes-not-messages.md)).

---

## Risks, and what is done about each

| Risk | Why it is real here | Mitigation |
|---|---|---|
| Phase 3 gets squeezed | It is the graded half and it sits mid-schedule | It is gated *before* Phase 4, not after. Analytics slips; consent does not. |
| Translations become a last-week casualty | Every project does this | Catalog structure lands in P2; missing keys throw in CI, so a skipped locale is a red build rather than a quiet English fallback. |
| One reviewer is a throughput ceiling | Srimoney reviews every PR | One ticket per PR, WIP capped at two per person, contract PRs jump the queue because people are blocked behind them. |
| Frontend blocked on backend | The classic failure of a layer split | Stubs are mandatory at G2 and the CI stub inventory makes skipping one visible. |
| A stub survives to the demo | It looks finished until someone clicks it | The stub inventory is printed on every CI run and must be empty at the P4 gate. |
| Committed seed dataset bloats the repo | It is committed so nobody needs a JDK | Size budget agreed when the dataset first lands; regeneration pinned to a fixed Synthea version and seed. |
| Horizontal split means nobody owns a feature | Three people must meet for anything to ship | The three gates are the meeting point, and they are merged code rather than a standup. |

---

## Conventions

Branches `feat/…` `fix/…` `chore/…` `docs/…`. Conventional commits, imperative, 72 characters. One ticket per PR. `main` protected: no direct pushes, CI green required, one approving review. No pre-commit hooks — they get bypassed and CI cannot be argued with.

Every non-obvious pattern gets an entry in [`learnings.md`](./learnings.md) as it lands, not at the end. The point of that file is that any of the four can explain any part of the codebase, including the parts they did not type.
