# Pulse — presentation script

18 slides. `/present` route. Split as requested: 1–7, 8–12, 13–18.

---

## Part 1 — Slides 1–7 (the story + the problem)

**1. Title**
"Pulse — a lifelong health record that the patient owns." Team: Shivansh Neekhra, Akshay VS, Bharadwaj B Chand, Srimoneyshankar Ajith. CSE312, IIIT Kottayam, guide Dr. Dhakshayani J.

**2. The accident**
9:42pm. Ravi, 34, walking home, hit by a car. Unconscious, no ID. Paramedics ask: blood group, allergies, medicines, who to call. Nobody can answer — his record exists, but it's split across three hospitals, and none of them are here.

**3. The scan**
At the hospital: the ambulance has no record, but Ravi's phone does. He'd made an emergency card and put the QR on the back of his phone. The paramedic scans it — signed in to the hospital system. Only the card opens. His full record stays closed.

**4. The card**
Four seconds later, the doctor knows what to avoid: no penicillin, asthma inhaler on hand. His wife gets called straight from the card. Nothing else was opened — the scan is logged and Ravi is notified afterward.

**5. Ask your record (Priya)**
Smaller moment: new city, new doctor, Priya forgets which tablets she's on. She asks her own record in plain language — "what medicines am I taking?" No AI model, fixed rules over her own data, nothing she asks is stored. Answer comes back with a receipt: 2 entries read, logged.

**6. Introduction**
That's Pulse: a lifelong health record where the patient decides. Four roles — Patients own and consent, Providers file (even for people who never registered), Clinicians read only inside active consent, Administrators keep identities clean but can never read clinical data. Built for India: four languages, synthetic data only, never a real patient.

**7. Problem and objectives**
Problem: records are scattered across hospitals and paper, emergency staff have nothing, access is implied and can't really be withdrawn, nobody can say who read what. Four objectives: **Own** — one record for life. **Consent** — enforced on every read, revoked immediately. **Account** — every access recorded and visible to the patient. **Reach** — four languages, an emergency path, mobile first.

---

## Part 2 — Slides 8–12 (requirements + architecture)

**8. Functional requirements**
Accounts (register, verify, step-up auth), Timeline (5 entry kinds, corrections never overwrite), Filing (provider staff file for anyone, even unregistered), Consent (scoped by type/date, revoked at once), Access log (every read visible + notified), Emergency card (QR + 60-min break-glass), Analytics (computed at request time), Ask your record (rule-based, 4 languages).

**9. Non-functional requirements**
Privacy (consent filter on every read, 404 not 403), Auditability (append-only by DB grant), Security (Argon2id, opaque Redis sessions, CSRF guard, default-deny routes), Integrity (no in-place edits, no clinical JSONB), Usability (4 locales, mobile-first), Maintainability (modular monolith, enforced boundaries), Testability (real Postgres, negative tests first), Deployability (one `docker compose up`, 6 services, seeded).

**10. System architecture**
One origin, one backend, one database. Browser → Caddy (same origin) → splits `/*` to Next.js 16, `/api/*` to FastAPI. FastAPI is a modular monolith — 11 modules (auth, users, patients, providers, records, consent, audit, notifications, analytics, admin, ask) — talking to PostgreSQL 18 for all durable data and Redis 8 for sessions only, never truth. Three adapters behind interfaces: Storage, Notification, Identity.

**11. Layers inside a module**
Each layer has one job it may not break: `routes.py` is HTTP only, `service.py` holds business rules (no SQL, no framework imports), `repository.py` holds all SQL, models + schemas define the shape. Modules talk through service interfaces, never each other's tables — a CI lint fails the build if they do.

**12. The consent query**
Every clinical read starts from one function, `accessible_entries`. Patient sees their own entries. Provider staff see only what their provider authored. Clinician sees what an active consent allows. Anyone else gets `false()` — default deny, not an afterthought bolted onto each endpoint.

---

## Part 3 — Slides 13–18 (consent engine, decisions, proof, close)

**13. Consent and revocation**
Four-step flow: patient grants (password re-check, scoped to types + date window) → clinician reads (filter passes, logged once) → patient revokes (no password needed, permission row deleted in the same transaction) → same clinician reads again (nothing cached, denied immediately). A 403 would confirm the person is a patient here — so denial is always 404.

**14. Key decisions (18 ADRs recorded)**
Highlight a few: opaque Redis sessions over JWT (logout/role changes apply server-side, instantly). One query builder for consent over per-endpoint checks (can't be forgotten in sixty places). Administrators read no clinical data over a superuser role (keeps the audit log safe for them to see). Append-only audit by DB `GRANT` over convention (app role literally cannot update/delete history).

**15. Patterns and practices**
Modular monolith, layered/repository pattern, ports and adapters, contract-first (OpenAPI → TypeScript types), fitness functions (route coverage + 4 CI lints), negative tests first. A rule that only lives in a doc gets broken by accident — these live in CI.

**16. Verification**
The risk is one missed filter, so that's what's tested hardest: backend tests on real Postgres, browser e2e tests plus one live run on the real stack, every endpoint declares a permission, every module boundary enforced, every decision has a written alternative, every interface string exists in all 4 languages.

**17. FAQ**
Why not JWT? → server-checked sessions, logout is instant. Why a monolith? → laptop-scale deploy, no scaling need, but boundaries linted as if extraction were coming. Why 404 not 403? → doesn't confirm the person is a patient. Is there an AI chatbot? → no model, fixed rules through the same consent filter. Why not translate diagnoses? → interface is localised, clinical text is not — translating it invents a medical claim. Is any data real? → none, Synthea + Indian overlay, synthetic, committed to the repo.

**18. Close**
"Patients own their history. Clinicians read it with consent. Every access is recorded." Team credits, repo link.

---

*Timing note: slides use build-steps (`data-builds`) — pause on each bullet/row reveal rather than reading the whole slide at once. Story slides (2–5) are voice-led, not read verbatim off the SVG.*
