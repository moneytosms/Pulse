# Video script

A fixed shot list for a recorded demo, not the live-presenter version.
`docs/demo.md` has the "why" after each step and branches for a live Q&A;
this is the scripted, no-branching cut — one path, one take, target
**~4 minutes**. Setup: `scripts/demo.sh` (resets seed data, brings the
stack up, prints the URLs and seeded logins below).

Three windows open before recording starts: Patient (normal window),
Clinician (private window), Mailpit. Screen recorder running on all three,
switch by alt-tab, no visible mouse hunting — know which window each cut
needs before hitting record.

| # | Time | Screen | Action | Voiceover |
|---|---|---|---|---|
| 1 | 0:00–0:20 | Patient window, `/en/register` | Type an email, a 12+ char password, submit. Cut to Mailpit, open "Verify your Pulse account", click the link. | "Pulse is a lifelong health record. Patients own it, providers add to it, clinicians read it only with consent — and every access is logged. Sign-up creates a Patient and sends a verification email; nothing leaves this laptop, it's caught locally." |
| 2 | 0:20–0:30 | Patient window, `/en/login` | Click quick-login **Patient (EN)** instead of the new empty account. | "Switching to a seeded patient with history, so there's something on the timeline." |
| 3 | 0:30–1:00 | Clinician window, `/en/login` → **Provider staff** → Patients → paste Patient ID → "File new entry" | Choose Diagnosis, set occurred-at, code system `ICD-10`, code `E11`, display name `Type 2 diabetes mellitus`, attach a PDF, submit, open the entry. | "Only Provider Staff can file — patients can't file their own entries. Entries are never edited in place; a correction inserts a new one and marks the old superseded, so the history never silently changes." |
| 4 | 1:00–1:15 | Patient window, `/en/timeline` | Scroll to the new entry at the top, point at the entry-type filter and the critical-result label. | "Chronological, filterable, and colour never carries meaning alone — there's always a label next to it." |
| 5 | 1:15–1:45 | Patient window, `/en/consent/new` | Enter `clinician0@example.com`, leave entry types unticked (grants all), purpose "Treatment", set expiry, enter password for step-up, submit. | "Consent goes to one named clinician, never a whole organisation, it always expires, and granting it asks for your password again — a deliberate speed bump in this direction only." |
| 6 | 1:45–2:05 | Clinician window, `/en/clinician` | Click the patient's name under "Patients who have given you access," open the Diagnosis entry. | "This only works because of that grant. The Clinician role alone gives nothing, and the list is never cached." |
| 7 | 2:05–2:20 | Patient window, `/en/audit` | Show the clinician's read: name, organisation, no clinical content. | "One audit event per access, not per row, and the table is append-only by database grant — not by convention." |
| 8 | 2:20–2:35 | Patient window, `/en/consent` | Click "Revoke," confirm. No password prompt. | "Revoking is deliberately the frictionless direction." |
| 9 | 2:35–2:50 | Clinician window, reload the record | Shows "Record not found." | "A 404, not a 403 — a 403 would confirm the person is a patient at all. Revocation applied mid-session because permissions are never cached, not even for a few seconds." |
| 10 | 2:50–3:15 | Clinician window → "Emergency access," write justification → Patient window, reload | Break-glass banner appears on the patient side. | "Emergencies aren't blocked, but they're loud: a CRITICAL audit event and an immediate notification to the patient." |
| 11 | 3:15–3:30 | Patient window, `/en/analytics` | Show lab trend, visit frequency, data-quality flags. | "Every chart is computed on page load through the same consent filter as the timeline — nothing stored to go stale or leak." |
| 12 | 3:30–3:45 | Admin login, `/en/admin/duplicates` | Show a candidate: name, DOB, phone, record count, no clinical content. Click "Merge," then "Reverse merge." | "Administrators see identity fields and counts, never clinical data, on any endpoint — and merges are human-only and reversible." |
| 13 | 3:45–4:00 | Any window, switch `/en` → `/hi` on the timeline | Point at the diagnosis text staying in English inside a Hindi UI. | "The interface translates. Clinical content doesn't — translating a diagnosis would mean inventing a medical claim." |

## Recording notes

- Reset before every take: `scripts/demo.sh` (wraps `docker compose down -v && up --build --wait`) — duplicate-review and consent state carry over otherwise, and step 12's queue needs an unreviewed candidate.
- Password for every seeded login: `Pulse@demo1`.
- If step 1's email doesn't land in Mailpit within a few seconds, check `docker compose logs backend | rg -i smtp`; the real demo path through Mailpit is proven in `npm run test:e2e:live` so a missed message is an environment hiccup, not a feature gap.
- Not shown: entry corrections (no screen files one — see `docs/demo.md` for the one line to say instead if asked live).
