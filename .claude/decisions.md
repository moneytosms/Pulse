# Decision Log

Architecture and significant design decisions. DocWriter agent maintains. Never delete entries.

Format:
```
## [YYYY-MM-DD] <decision>
Context: <why this decision was needed>
Options: <what was considered>
Chosen: <what was picked>
Rejected: <what was dropped and why>
```

This log is the index. The long-form argument for anything hard to reverse lives in `docs/adr/`; this file exists so the shape of a decision is findable without reading eleven documents.

---

## [2026-08-18] Modular monolith, not microservices
Context: Ten business domains, four developers, a Compose stack on a laptop as the deployment target.
Options: microservices per domain; layered monolith; modular monolith with domain modules.
Chosen: modular monolith — one FastAPI app, one PostgreSQL database, module boundaries drawn as if extraction were coming.
Rejected: microservices — independent deployment and scaling are unrealisable here, while network hops, distributed transactions and ten times the operational surface are entirely real. Layered-only — it puts the boundary in the wrong place; the interesting coupling is between domains, not between layers.

## [2026-08-18] Medical Entry uses joined-table inheritance
Context: Five clinical entry kinds sharing about eight fields and diverging in twenty-five. ADR-0001.
Options: one wide sparse table; a JSONB payload column; joined-table inheritance.
Chosen: one `medical_entry` trunk plus one table per kind, SQLAlchemy polymorphic, `selectin_polymorphic` on reads.
Rejected: wide table — mostly-null columns and no per-kind constraints. JSONB — unqueryable, untypeable, and invisible to consent scoping, which destroys the argument for typed clinical data.

## [2026-08-18] Patient is the aggregate root; Patient Record is deleted
Context: The rough schema carried both a Patient and a Patient Record entity with no clear split. ADR-0002.
Options: keep both; collapse into Patient; collapse into Patient Record.
Chosen: collapse into Patient. `patient.user_id` stays nullable so Providers can file for someone who has never registered.
Rejected: keeping both — two entities meaning one thing, and every query has to pick.

## [2026-08-18] Opaque Redis sessions, not JWTs
Context: Consent revocation must take effect immediately, mid-session. ADR-0003.
Options: JWT access tokens; JWT plus a denylist; opaque server-side sessions.
Chosen: random opaque tokens in Redis keyed by `sha256(token)`, `HttpOnly` cookie, 60min idle / 12h absolute.
Rejected: JWT — valid until expiry by design, so the server has no say. Adding a denylist recovers revocation but reintroduces server-side state, which was the only reason to use JWT.

## [2026-08-18] Route authorization is default-deny, enforced by a CI test
Context: The realistic failure in a nine-module system is a *missing* permission check on an endpoint added under deadline. ADR-0004.
Options: check inside handlers by convention; a decorator with a code-review rule; a declared dependency plus a test that enumerates routes.
Chosen: `requires(Permission)` dependency, explicit public marker where genuinely public, CI test failing on any route declaring neither.
Rejected: convention — it produces a working endpoint that returns other people's medical records, and review does not reliably catch an absence.

## [2026-08-18] Consent is enforced by one query builder
Context: Access rules spread across call sites are access rules with holes. ADR-0006, ADR-0010.
Options: service-layer checks per endpoint; a decorator; a single repository-level query filter.
Chosen: `accessible_entries(actor, patient_id)` — every clinical read composes from it, plus a CI lint against raw `select(MedicalEntry)`. Grants go to individual Clinicians, never organisations. No permission decision is cached anywhere.
Rejected: per-endpoint checks — sixty places to be right, and the one that is wrong is silent. Caching — it makes immediate revocation false.

## [2026-08-18] Audit log is append-only by database grant
Context: An audit story that permits silent `UPDATE`s is not worth much. ADR-0008.
Options: application-level discipline; ORM hooks; database `GRANT` restriction.
Chosen: two database roles; the application role holds `INSERT` and `SELECT` only. Events emitted explicitly in the service layer.
Rejected: ORM hooks — the most important events are *reads*, which produce no write for a hook to fire on. Convention — unenforceable and unprovable to an examiner.

## [2026-08-18] Administrators cannot read clinical data
Context: Someone has to run the system without being able to read patients' histories. ADR-0007.
Options: admin read access with audit logging; admin read behind break-glass; no admin clinical access at all.
Chosen: none, on any endpoint. Administrators get the full audit log instead — which is safe precisely because it contains no clinical content.
Rejected: audited admin access — "we log it" is not consent, and it makes the audit log a clinical data store.

## [2026-08-18] Analytics are computed on read
Context: The rough schema had a `summary_insight` table. ADR-0009.
Options: materialised insight rows; a cache; computed on read through the consent filter.
Chosen: computed on read, composed from `accessible_entries`. No table.
Rejected: stored insights — a stored row has no actor, so there is nowhere to apply the consent filter, and it becomes a second clinical data store outside access control. Medication adherence excluded entirely: prescriptions do not tell you what was taken.

## [2026-08-18] Consent scope is entry-type plus date window; expiry mandatory
Context: Scoping needs to be meaningful without being a UI nobody completes. ADR-0010.
Options: all-or-nothing; per-entry selection; entry-type plus optional date window.
Chosen: entry types plus optional date window, mandatory expiry (30 days default, one year maximum, renewable), break-glass as the emergency path — time-boxed, justified, loud.
Rejected: per-entry ticking — "choose nine of your two hundred entries" is abandoned halfway. Never-expiring consent — nobody revisits it.

## [2026-08-18] Merges are human-initiated and reversible
Context: Duplicate Patients are inevitable when Providers create unclaimed Patients. ADR-0011.
Options: auto-merge above a score threshold; human review; human review with reversal.
Chosen: human-only, tombstoned, reversible. Trigram scoring on token-sorted names, blocking before scoring.
Rejected: auto-merge — merging two people's medical histories wrongly is the worst failure this system can produce. Soundex/Metaphone — English phonetics, poor on romanised Indian names.

## [2026-08-18] Interface is localised; clinical data is not
Context: Four locales ship — English, Hindi, Tamil, Malayalam. ADR-0013.
Options: translate everything including clinical content; translate the interface only.
Chosen: interface only. API returns machine-readable error codes plus an English default message; notifications store type plus params and render at read time.
Rejected: translating clinical content — a translated diagnosis is a medical claim the system cannot stand behind, and a mistranslated dosage is a safety issue rather than a formatting one.

## [2026-08-18] Same-origin reverse proxy
Context: Cookie authentication plus two origins means `SameSite=None`, CORS preflights, and bugs that only appear off the author's laptop. ADR-0012.
Options: CORS between two ports; Next.js rewrites proxying to the API; one Caddy in front of both.
Chosen: Caddy routes `/api/*` to FastAPI and everything else to Next.js.
Rejected: CORS — a whole bug category kept alive to avoid six lines of config.

## [2026-08-22] Ownership is horizontal by layer, not vertical by feature
Context: The map assumed vertical ownership — one person per module, front to back. The team's actual strengths are layer-shaped: Shivansh on the database, Akshay on the backend, Bharadwaj on the frontend, Srimoney on platform, integration and review.
Options: keep vertical ownership; horizontal by layer; hybrid with vertical demo-spine ownership.
Chosen: horizontal, with three merge gates per module — contract, stub, implementation — as the coordination mechanism, and Srimoney floating into whichever layer is behind.
Rejected: vertical — it would have each person writing SQL, services and React in a stack none of them has yet used in anger, on a two-month clock. The cost accepted with horizontal: no feature is finished by one person, so the contracts between layers become the project's most important artifact. See `docs/delivery-plan.md`.

## [2026-08-22] Phase 3 gates Phase 4
Context: Consent, audit and notifications are the graded half and sit mid-schedule, where a slip usually eats them.
Options: run P3 and P4 in parallel to buy slack; hard gate P4 behind P3.
Chosen: hard gate. Nothing from P4 starts until the full demo spine works and every negative access test is green.
Rejected: parallel — it converts a schedule risk into a grade risk, in exchange for finishing analytics that nobody is grading.
