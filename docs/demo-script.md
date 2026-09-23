# Demo script

A step-by-step script for the live demo, covering the full spine from
issue #56 (signup → upload → timeline → grant → clinician read → patient
audit view → revoke → clinician locked out) plus a pass through Phase 4's
analytics, admin dashboard and duplicate-review screens.

**Rehearsal status:** walked through once, end to end, against `docker
compose up --build` on the author's existing clone, before the shadcn/ui
rebuild (PR #59). **Not** yet re-rehearsed against the rebuilt UI, **not**
on a fresh `git clone`, and not by anyone other than the author. Issue #56
asks for a rehearsal on a machine that is not the author's; that has not
happened and should not be assumed done.

Screen names, labels and buttons below were re-checked on 2026-09-23
against the English catalogs (`frontend/src/i18n/messages/en/`) at the
post-#59 tree. That is a check against the source, not a live rehearsal.

## Setup (before the audience is in the room)

```bash
git clone https://github.com/moneytosms/Pulse.git   # or cd into an existing clone
cd Pulse
docker compose up --build      # or: uv run run.py  (backend healthy first, then frontend)
```

Always pass `--build`. Without it, Compose reuses whatever image already
exists, and an old frontend image serves an old build: the landing page
loads but every other route 404s. `run.py` always builds.

Wait for all six containers healthy (`docker compose ps`). First boot runs
migrations and seeds identity data automatically — no separate seed step.

- App: `http://localhost` (Caddy, port 80). Port 3000 is not published to
  the host by design (ADR-0012): the browser must reach `/api` on the same
  origin.
- Mailpit inbox (verification emails): `http://localhost:8025`

Seeded accounts all use the password `Pulse@demo1` and have quick-login
buttons on `/en/login`: **Patient (EN)** (`demo.patient.en@example.com`),
**Patient (HI)**, **Provider staff**, **Clinician**
(`clinician0@example.com`) and **Administrator** (`admin0@example.com`).
The Administrator has no Patient row, by construction (ADR-0007).

## Part 1 — the demo spine (#56)

All of this is one continuous story about **Priya**, a patient, and **Dr.
Fathima Rasheed**, a clinician who initially has no access to her record.

1. **Signup.** Go to `/en/register`. Fill in an email, a password, choose
   "Patient", submit. Land on "Confirm your email address"
   (`/en/verify-pending`). Open `http://localhost:8025`, find the
   verification email, click the link. Say: *every account starts
   unverified — this is the DPDP-shaped consent story starting at account
   creation, not at first clinical read.*

2. **Log in** as the new account (or use the **Patient (EN)** quick-login
   button on `/en/login` — `demo.patient.en@example.com` — to skip ahead
   with a patient who already has history).

3. **Upload.** Copy the **Patient ID** from `/en/profile` ("Your
   profile"); the entry form asks for it. For `demo.patient.en` it is
   `0c96112a-1653-5403-999c-30ec1ef6dda8`. Go to `/en/timeline/new`. File
   a Diagnosis entry: pick "Diagnosis", set "Occurred at", code system "ICD-10", code
   "E11", display name "Type 2 diabetes mellitus". Submit → "View entry".
   Say: *this is a Provider or the patient themself filing a Medical
   Entry — never editable in place after this point, only superseded.*

4. **Timeline.** Go to `/en/timeline`. The filed entry appears, newest
   first. Point out the entry-type filter and the "Critical" label (never
   colour alone — `frontend.md`).

5. **Grant consent.** Go to **Access** (`/en/consent`) → "Grant access"
   (`/en/consent/new`). "Clinician email": `clinician0@example.com`.
   Leave every "Entry types" box unticked to grant all types. "Purpose":
   "Treatment". Set "Access expires". Submit → "Access granted". An
   email that is not a registered Clinician is rejected ("No clinician is
   registered with that email."). Say: *consent
   is granted to one named clinician, never an organisation, and it always
   has a mandatory expiry.*

6. **Clinician reads the record.** Open a second (private/incognito)
   window, log in as **Clinician** (`clinician0@example.com` quick-login).
   It lands on "Clinician access" (`/en/clinician`, nav: **Patients**).
   Paste the Patient ID into "Patient ID" → "Open record". "Patient
   record" lists the Diagnosis entry. Say: *this read is happening because of the consent grant, not
   because of the clinician's role — a Clinician role alone grants
   nothing.*

7. **Patient's own audit view.** Back in Priya's window, go to `/en/audit`
   — "Who accessed my records". The clinician's read appears, with the
   clinician's name and provider organisation, never any clinical content.
   Say: *this is one row per access, not per entry viewed — a 50-entry
   timeline read is still one `ENTRY_VIEWED` audit event.*

8. **Revoke.** Go to `/en/consent`, find the clinician's grant, click
   "Revoke", confirm. No step-up verification is asked here — say: *this
   is deliberate; withdrawing access must be the frictionless direction.*

9. **Clinician locked out.** Back in the clinician's window, reload the
   patient record page. It now shows "Record not found" —
   the exact same message a genuinely nonexistent patient ID would
   produce. Say: *this is a 404, not a 403 — a 403 would confirm the
   record exists, which itself is sensitive information. Revocation took
   effect immediately, mid-session, because permission is never cached.*

   *Optional:* the same screen offers **Emergency access** (break-glass):
   a written justification opens the record for 60 minutes, is recorded
   in the audit log, and the patient sees an "Emergency access to your
   record" banner.

## Part 2 — Phase 4 screens

Still as the patient from Part 1 (needs a few filed entries with lab
values to show something on the analytics screen — the seeded demo
patients have this already; a freshly-registered account filed in Part 1
will look sparse, so switch to `demo.patient.en@example.com` for this
part if you started from a brand-new signup).

10. **Analytics.** Go to `/en/analytics` — "Your health analytics". Walk
    through visit frequency, active medications, and the data-quality
    flags section (e.g. "No contact phone number is on file for you.").
    Say: *every chart here is computed on read, through the same
    consent-aware query path as the timeline — there is no stored insight
    table to go stale or leak.*

11. **Admin dashboard.** Switch to the **Administrator** quick-login
    (`admin0@example.com`) on `/en/login`. Go to `/en/admin`. Say: *an Administrator reads no clinical data on
    any screen, ever — this dashboard only ever shows identity fields and
    counts.*

12. **Duplicate review.** Click through to `/en/admin/duplicates`. If the
    queue is empty, say so plainly rather than skipping the screen —
    the seeded planted-duplicate pairs may already have been reviewed in
    an earlier session. If a candidate is present: point out that only
    name, date of birth, phone, account status and "Records on file" are
    shown. Walk through "Merge", then find it under "Reversible merges",
    which lists every unreversed merge by any administrator, across
    sessions. "Reverse merge" moves the entries back. "Not a duplicate"
    dismisses a candidate without merging.

## Fallback notes

- If Mailpit shows no email after signup, check `docker compose logs
  backend` for an SMTP connection error before assuming the account
  didn't register — registration and email delivery are decoupled.
- Locale switching (`/en` ↔ `/hi` ↔ `/ta` ↔ `/ml`) works on every screen
  above; see `docs/locale-review.md` before demonstrating Tamil or
  Malayalam screens, since neither has had a native-speaker review pass.
