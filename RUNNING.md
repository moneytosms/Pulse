# Running Pulse

A from-clone, exact-values walkthrough: how to bring the stack up, how to
verify it, and a concrete order of screens/inputs to exercise against the
committed demo data. For the narrated live-demo version (with the "why"
after each step) see [`docs/demo-script.md`](docs/demo-script.md) — this
document is the flatter reference: every field, every button, every seeded
value, in one place.

Checked against the tree at commit `f3c15f2` (2026-09-15). The seeded
Administrator (`admin0@example.com`) landed in that commit — this doc does
**not** carry the old "promote a user by hand" workaround that
`docs/demo-script.md` still documents as a known gap; that gap is closed.

## 1. Prerequisites

- Docker + Docker Compose. Nothing else — no Node, no Python, no JDK
  needed to *run* the stack; those are only for local dev/regeneration
  (see [`docs/tech-stack.md`](docs/tech-stack.md), [`seed/README.md`](seed/README.md)).
- Ports `80` (app) and `8025` (Mailpit) free on the host.

## 2. Bring the stack up

```bash
git clone https://github.com/moneytosms/Pulse.git
cd Pulse
docker compose up --build      # or: uv run run.py  (backend healthy first, then frontend)
```

Always pass `--build`: without it Compose reuses an existing image, and a
stale frontend image serves the landing page while every other route 404s.
The app is on port 80 via Caddy; port 3000 is not published to the host.

Wait for all six containers healthy:

```bash
docker compose ps
```

Services: `caddy` (reverse proxy, port 80), `frontend` (Next.js), `backend`
(FastAPI), `postgres:18.6`, `redis:8.8.2`, `mailpit` (SMTP inbox, port 8025).

First boot runs `alembic upgrade head` then the seed loader automatically —
no separate seed step. It's idempotent (a `seed_marker` row), so a second
`docker compose up` changes nothing.

- App: **http://localhost**
- Mailpit (verification emails land here, not a real inbox): **http://localhost:8025**

## 3. Verify it actually came up

```bash
docker compose ps                                   # all 6 "healthy"/"running"
docker compose logs backend | grep -i seed           # loader ran, no errors
curl -s http://localhost/api/v1/patients/me -o /dev/null -w '%{http_code}\n'   # 401 (no session yet) — proves Caddy → backend routing works
```

If `docker compose logs backend` shows an SMTP connection error, that's
independent of signup succeeding — registration and email delivery are
decoupled (see fallback notes in `docs/demo-script.md`).

## 4. Seeded accounts — exact values

Every row below is real, committed data (`seed/data/identity/users.csv`),
loaded on first boot. Password is the same for all of them:

```
Pulse@demo1
```

| Email | Role | Locale | User ID | Patient ID | Quick-login button on `/en/login`? |
|---|---|---|---|---|---|
| `demo.patient.en@example.com` | PATIENT | en | `dabb4d62-9ed8-5759-8e9b-a6bc4578a1a1` | `0c96112a-1653-5403-999c-30ec1ef6dda8` | Yes — "Patient (EN)" |
| `demo.patient.hi@example.com` | PATIENT | hi | `c3ae3186-43bc-5c9f-be8d-50b70f50dda0` | `3688d458-8442-5c8a-863d-362215ef3c6c` | Yes — "Patient (HI)" |
| `staff000@example.com` | PROVIDER_STAFF | — | `b5f9a2d3-fc91-5ab5-b929-38345a555876` | — | Yes — "Provider staff" |
| `clinician0@example.com` | CLINICIAN | — | `44e4531e-4149-513f-95d5-343a942af00b` | — | Yes — "Clinician" |
| `admin0@example.com` | ADMINISTRATOR | — | `d65c5296-b1f6-5de1-9289-933d41e3de24` | — | Yes — "Administrator" |

`demo.patient.en`'s patient row is "Aishani Toor"; `demo.patient.hi`'s is
"माननीय रघु गावडे". These are the two Patient IDs to type anywhere a screen
asks for one (timeline entry filing, consent grants, clinician record
reads) — there is no patient search/picker UI yet, by design (no
speculative UI ahead of a real search screen).

Every other seeded row (≈98 more users) gets a random, unusable password
hash — don't bother trying them. Full generation/regeneration details:
[`seed/README.md`](seed/README.md).

## 5. Exact walkthrough, in order

This mirrors `docs/demo-script.md`'s spine but written as literal field
values, so you can follow it without also reading the narration. Locale
prefix is `/en` throughout — swap for `/hi`, `/ta`, `/ml` to check other
locales (see §7).

### 5.1 Fresh signup (optional — or skip to 5.2 with seeded accounts)

1. `http://localhost/en/register`
   - **Email**: any address, e.g. `test.patient@example.com`
   - **Password**: 12+ characters — the form rejects shorter (`MIN_PASSWORD = 12`), e.g. `TestPassword123!`
   - **Role**: one of Patient / Clinician / Provider staff / Administrator — pick **Patient**
   - Submit → redirected to `/en/verify-pending?email=...`
2. Open `http://localhost:8025`, find the verification email, click the link.
3. Log in at `/en/login` with the same email/password.

> Registering as **Administrator** is technically possible through this
> same form (the role dropdown has no restriction) — worth knowing if
> you're testing access control, since it means admin isn't
> invite-only in the current build.

### 5.2 Log in with a seeded account

`/en/login` → click **Patient (EN)** (or type
`demo.patient.en@example.com` / `Pulse@demo1` by hand). This account
already has seed history, unlike a brand-new signup.

### 5.3 File a Medical Entry — `/en/timeline/new`

Field set changes based on **Entry type**; here's what to fill for each:

**Common to every entry type:**
- **Patient ID**: `0c96112a-1653-5403-999c-30ec1ef6dda8` (demo.patient.en's patient row — or your own if freshly registered and you know your ID from `seed`/DB)
- **Entry type**: one of Diagnosis / Prescription / Lab report / Procedure / Clinical note
- **Occurred at**: any past datetime, e.g. `2026-01-15T09:30`
- **Critical** checkbox: leave unchecked unless you specifically want the "Critical" label to show on the timeline

**Diagnosis / Procedure / Lab report** (coded types) add:
- **Code system**: `ICD-10` (Diagnosis) — for Lab report use `LOINC`, for Procedure use `SNOMED-CT`
- **Code**: `E11` (matches "Type 2 diabetes mellitus" — a real ICD-10 code, not invented)
- **Display name**: `Type 2 diabetes mellitus`

**Lab report** additionally:
- **Value (numeric)**: `142`
- **Value (text)**: leave blank if numeric is set (a lab result is one or the other — cultures use text, e.g. `Positive`)
- **Unit**: `mg/dL`
- **Reference low / high**: `70` / `100`

**Prescription** instead of the coded fields:
- **Medication name**: `Metformin`
- **Dosage**: `500 mg`
- **Frequency**: `Twice daily`
- **Route**: `Oral`

**Clinical note** instead:
- **Text**: any free text, e.g. `Follow-up in 3 months, patient reports improved adherence.`

**File** (optional, all types): PDF/PNG/JPEG only (`accept="application/pdf,image/png,image/jpeg"`), 25 MiB app-level cap.

Submit → "View entry" link → confirms it landed.

### 5.4 See it on the timeline — `/en/timeline`

Newest-first list. Filter by entry type; critical entries carry both a
label *and* an icon (never colour alone, per `frontend.md`).

### 5.5 Grant consent — `/en/consent/new`

- **Clinician email**: `clinician0@example.com` (seeded Clinician). An email that is not a registered Clinician is rejected
- **Entry types**: leave every checkbox unticked to grant all types (ticking is a filter, not a whitelist you must complete — unticked means "no filter" on the wire)
- **From / To date**: optional — leave blank for no date window
- **Purpose**: `Treatment` (or `Second opinion` / `Other` — if Other, a free-text **Purpose (other)** field appears)
- **Expires at**: any future datetime, e.g. one week out
- Submit → "Access granted"

### 5.6 Clinician reads the record

Open a private/incognito window → `/en/login` → **Clinician** quick-login
(`clinician0@example.com`) → go to:

```
/en/patients/0c96112a-1653-5403-999c-30ec1ef6dda8/records
```

(swap in whichever patient ID you granted consent for). The entry from
5.3 is visible — this is the consent grant working, not the Clinician
role alone.

### 5.7 Patient's own audit view — `/en/audit`

Back in the Patient window. Shows the clinician's read: name + provider
org, timestamp — never clinical content, one row per access (not per
entry viewed).

### 5.8 Revoke — `/en/consent`

Find the grant to Clinician → **Revoke** → confirm. No step-up
verification here — revocation is deliberately frictionless.

### 5.9 Confirm the clinician is locked out

Reload the same `/en/patients/{patientId}/records` URL in the clinician's
window → "Record not found" (a 404 — same message a nonexistent ID would
give, never a 403).

### 5.10 Analytics — `/en/analytics`

Best with a seeded account that already has history — `demo.patient.en`
or `demo.patient.hi`, not a bare fresh signup. Shows visit frequency,
active medications, data-quality flags (e.g. missing phone number). All
computed on read through the same consent-aware path as the timeline.

### 5.11 Admin dashboard — `/en/admin`

Log in as **Administrator** (`admin0@example.com` / `Pulse@demo1` — no
manual SQL promotion needed anymore). Identity fields and counts only;
zero clinical data on this screen or any admin screen, by construction
(ADR-0007).

### 5.12 Duplicate review — `/en/admin/duplicates`

Still as Administrator. Seeded planted pairs
(`seed/data/identity/planted_pairs.csv`) populate the queue: 3 true
duplicates (token-order-swap, DOB-typo, initials-vs-expanded variants)
plus 2 near-miss siblings that should **not** merge. If empty, an earlier
session already reviewed everything — that's expected, say so rather than
treating it as broken. "Merge" is reversible: every unreversed merge, by any
administrator, is listed under "Reversible merges" with a "Reverse merge"
button, across sessions.

### 5.13 Notifications — `/en/notifications` and `/en/notifications/preferences`

Any account. Preferences screen is toggle-only (per-channel opt in/out),
no free-text input to fill.

## 6. Backend verification (without the browser)

```bash
cd backend
uv run pytest -q                              # 205 tests, needs Docker (testcontainers: real Postgres + Redis)
uv run ruff check .
uv run mypy .
uv run python scripts/lint_cross_module_imports.py
uv run python scripts/lint_entry_query.py
uv run python scripts/lint_actor_first.py
uv run python scripts/stub_inventory.py       # should report 0 — no @stub endpoints remain
```

## 7. Frontend verification

```bash
cd frontend
npm ci
npm run lint
npx tsc --noEmit
npm run build
```

```bash
npx playwright install --with-deps chromium   # once
npx playwright test                            # 23 e2e specs, fully mocked — no running stack needed
```

Locale switching works on every screen above — swap the path prefix
(`/en` ↔ `/hi` ↔ `/ta` ↔ `/ml`). Tamil and Malayalam have **not** had a
native-speaker review pass yet (`docs/locale-review.md`) — expect
possible awkward phrasing there, not missing strings (missing keys throw
in dev/CI, never silently fall back outside production).

## 8. Seed regeneration (only if you touched `seed/scripts/` or the schema)

Needs a JDK — see [`seed/README.md`](seed/README.md#regenerating-needs-java)
for the full pinned toolchain. Not needed for normal running/testing.

## 9. Tearing down

```bash
docker compose down            # stop, keep the seeded Postgres volume
docker compose down -v         # stop AND wipe the volume — next `up` reseeds from scratch
```

## Known gaps / things this doc deliberately does not paper over

- No patient search/picker UI — every screen that needs a Patient ID
  (timeline/new, consent/new) takes it as a plain text field. Use the IDs
  in §4.
- Registration's role dropdown includes Administrator with no gating —
  see the callout in §5.1.
- Tamil/Malayalam: machine-translated, unreviewed by a native speaker.
