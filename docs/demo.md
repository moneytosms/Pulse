# Demo

The exact workflow for the live demo. It covers every user-facing feature,
in an order that tells one story: a Patient owns their record, a Clinician
reads it only with consent, every access is recorded, and withdrawing
consent takes effect immediately.

Exact seeded IDs, the backend checks and the teardown steps are in
[`RUNNING.md`](../RUNNING.md). This file covers what to click and what to
say while doing it.  

## Status: read before rehearsing

- **Fixed 2026-09-28:** the consent grant form now asks for the password
  and calls `/auth/step-up` first, and only Provider Staff see "File new
  entry" (patients can't file; the button used to return 403). Both
  checked against the live stack. The e2e suite mocks the API, so a live
  run is still the only proof that the real backend agrees.
- **Rehearsal:** one walk-through, on the author's own clone, before the
  shadcn/ui rebuild (PR #59). It has not been re-rehearsed on the rebuilt
  UI or on a fresh `git clone`, and nobody other than the author has
  run it. #56 asks for a rehearsal on a machine that is not the author's.
- **Locales:** Hindi, Tamil and Malayalam have not been reviewed by a
  native speaker. See [`locale-review.md`](locale-review.md).

## Feature coverage

| Feature | Step |
|---|---|
| Registration, email verification (Mailpit) | 1 |
| Seeded logins, one per role | 2 |
| Provider Staff files a Medical Entry (coded fields, document attachment) | 3 |
| Timeline: chronological, filterable by type, label as well as colour | 4 |
| Consent grant: one named clinician, scoped, mandatory expiry, step-up | 5 |
| Clinician reads a record with consent | 6 |
| "Who accessed my records" audit view | 7 |
| Revoke with no step-up | 8 |
| Immediate lockout with 404, not 403 | 9 |
| Break-glass emergency access, patient banner, CRITICAL audit | 10 |
| Notifications and per-channel preferences | 11 |
| Analytics computed on read through `accessible_entries` | 12 |
| Admin dashboard with no clinical data | 13 |
| Duplicate review, human-only merge, reversal | 14 |
| Four locales; clinical content never translated | 15 |

Not demonstrable in the UI: corrections. The backend supersedes entries
and the entry detail screen shows "This entry corrects an earlier one.",
but no screen files a correction. Mention it at step 3 instead of showing it.

## Email verification: local Mailpit or Gmail SMTP

The default Compose setup uses Mailpit, a local fake mail server. It accepts
messages on SMTP port 1025 and displays them at `http://localhost:8025`; it
does not deliver to real inboxes. This keeps a fresh clone runnable without
credentials.

**To send through the configured personal Gmail account**, copy `.env.example`
to `.env` and replace `SMTP_PASSWORD` with a Google App Password. Keep
`SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, and `SMTP_STARTTLS=true`. The App Password is used instead of
the normal Google password; Google requires 2-Step Verification for App
Passwords. Keep `.env` out of Git. The same variables can be set as deployment
secrets for a hosted app.

Google links: [Gmail SMTP settings](https://support.google.com/a/answer/176600)
and [App Password requirements](https://support.google.com/accounts/answer/185833).

**Configuration:** with no `.env`, Compose uses the Mailpit defaults. When
`.env` is present, Compose passes its SMTP settings into the backend:

| Setting | Where | Value |
|---|---|---|
| `SMTP_HOST` / `SMTP_PORT` | backend env | `mailpit` / `1025` by default; Gmail uses `smtp.gmail.com` / `587` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | local `.env` or deployment secrets | Gmail address / App Password; blank for Mailpit |
| `SMTP_STARTTLS` / `SMTP_SSL` | backend env | `false` / `false` by default; Gmail uses `true` / `false` |
| `PUBLIC_BASE_URL` | backend env | Defaults to `http://localhost`; use a public HTTPS URL for recipients outside this machine |
| `MAIL_FROM` | backend env | Defaults to the SMTP username, or `no-reply@pulse.local` for Mailpit |
| Mailpit inbox | `mailpit` publishes `8025` | `http://localhost:8025` when using the default configuration |

**Flow:** register, and the backend stores a challenge in Redis (it
expires) and emails the link
`{PUBLIC_BASE_URL}/{locale}/verify?challenge=…&token=…`. Open it from
Mailpit and the account is verified.

For a Gmail message opened on the same development machine,
`PUBLIC_BASE_URL=http://localhost` is fine. If the recipient is someone else,
the link must use an HTTPS hostname or tunnel they can reach; `localhost` in
their browser points to their own machine. Automated tests use fake email
providers and never send messages through Gmail.

## Setup (before the audience is in the room)

```bash
git clone https://github.com/moneytosms/Pulse.git && cd Pulse
docker compose up --build      # or: uv run run.py
docker compose ps              # wait until all six are healthy
```

Always pass `--build`. Without it, Compose reuses an old frontend image:
the landing page loads but every other route returns 404.

To start from clean seed data (safe, because the seed is deterministic):

```bash
docker compose down -v && docker compose up --build
```

Open three windows:

1. **Patient:** `http://localhost/en/login`
2. **Clinician:** a private window, `http://localhost/en/login`
3. **Mailpit:** `http://localhost:8025`

All seeded accounts use the password `Pulse@demo1` and have quick-login
buttons on `/en/login`.

| Button | Email | Patient ID |
|---|---|---|
| Patient (EN) | `demo.patient.en@example.com` | `0c96112a-1653-5403-999c-30ec1ef6dda8` |
| Patient (HI) | `demo.patient.hi@example.com` | `3688d458-8442-5c8a-863d-362215ef3c6c` |
| Provider staff | `staff000@example.com` | none |
| Clinician | `clinician0@example.com` | none |
| Administrator | `admin0@example.com` | none (ADR-0007) |

Keep the Patient ID above ready to paste. There is no patient search.

## Part 1: consent and access (the graded spine)

1. **Register and verify.** Go to `/en/register`. Enter any email and a
   password of at least 12 characters (for example `TestPassword123!`) and
   submit — sign-up creates a Patient, so there is no role choice. You land
   on "Confirm your email address".
   In Mailpit, open "Verify your Pulse account" and click the link.
   *Say:* every account starts unverified, and the email went to a local
   catcher, so nothing leaves this laptop.

2. **Log in with history.** In the Patient window, click **Patient (EN)**.
   A new signup has an empty record, so the rest of the demo uses a
   seeded patient.

3. **File an entry (as Provider Staff).** Only Provider Staff can file.
   In the Clinician window, click **Provider staff**. Under **Patients**,
   paste the Patient ID, click "Open record", then **File new entry**.
   The Patient ID is already filled in. Choose "Diagnosis" and set
   "Occurred at". Enter code system `ICD-10`, code `E11` and display name
   `Type 2 diabetes mellitus`. Attach a PDF and point out the upload
   progress. Submit, then click "View entry". Log this window out after.
   *Say:* providers contribute records and patients own them; a Patient
   can't file clinical entries. Entries are never edited in place. A
   correction inserts a new entry and marks the old one superseded.

4. **Timeline.** In the Patient window, go to `/en/timeline`. The new
   entry is on top. Show the entry-type filter and the "Critical" label on an abnormal lab.
   *Say:* colour never carries meaning alone; there is always a label.

5. **Grant consent.** Go to **Access**, "Grant access" (`/en/consent/new`). Enter
   `clinician0@example.com` as "Clinician email" and leave all "Entry
   types" unticked, which grants every type. Set "Purpose" to
   "Treatment" and set "Access expires". Enter `Pulse@demo1` in "Confirm
   with your password" (step-up) and submit.
   *Say:* consent goes to one named clinician, never an organisation, it
   always expires, and granting it asks for your password again.
   Also show that an email which is not a registered clinician gets
   "No clinician is registered with that email."

6. **Clinician reads.** In the Clinician window, click **Clinician**.
   You land on "Clinician access" (`/en/clinician`). Click the Patient's
   name under "Patients who have given you access". The Diagnosis entry
   is listed. Open it.
   *Say:* this works because of the consent grant. The Clinician role on
   its own gives no access, and the list is never cached — revoke it and
   the name disappears on the next load, not on some later expiry.

7. **Audit view.** In the Patient window, open `/en/audit` ("Who
   accessed my records"). The clinician's read is listed with their name
   and organisation and no clinical content.
   *Say:* one audit event per access, not per row. The audit table is
   append-only by a database GRANT.

8. **Revoke.** Go to `/en/consent`, click "Revoke" on the grant and
   confirm. There is no password prompt.
   *Say:* withdrawing access is deliberately the easy direction.

9. **Lockout.** In the Clinician window, reload the record. It shows
   "Record not found", the same as for a patient ID that doesn't exist.
   *Say:* this is a 404, not a 403, because a 403 would reveal that the
   person is a patient. Revocation applied mid-session because
   permissions are never cached.

10. **Break-glass.** On the same screen, use **Emergency access**. Enter a
    written justification. The record opens for 60 minutes. In the
    Patient window, reload: an "Emergency access to your record" banner
    appears, and the access is in `/en/audit`.
    *Say:* emergencies aren't blocked, but they are loud: a CRITICAL
    audit event and an immediate notification to the patient.

11. **Notifications.** As the patient, open `/en/notifications`. The
    break-glass notice is there. Open `/en/notifications/preferences`.
    *Say:* mandatory events (break-glass, for example) don't appear as
    toggles at all, because they can't be turned off. Notifications carry
    no clinical data.

## Part 2: analytics, admin, deduplication, locales

12. **Analytics.** As **Patient (EN)**, open `/en/analytics`. Show the lab
    trend picker, visit frequency, active medications and the data-quality
    flags.
    *Say:* every chart is computed when the page loads, through the same
    consent filter as the timeline. There is no stored insight table to
    go stale or leak.

13. **Admin dashboard.** Log in as **Administrator** and open `/en/admin`.
    *Say:* administrators see identity fields and counts only, never
    clinical data, on any endpoint.

14. **Duplicate review.** Open `/en/admin/duplicates`. A candidate shows
    name, date of birth, phone, account status and "Records on file", and
    nothing clinical. Click "Merge". It appears under "Reversible merges";
    "Reverse merge" undoes it, and "Not a duplicate" dismisses a
    candidate. If the queue is empty, earlier sessions reviewed the seeded
    pairs: say so, or reset with `docker compose down -v`.
    *Say:* the seed plants duplicates and near-miss non-duplicates, so
    precision can be measured. Merges are human-only and reversible.

15. **Locales.** Log in as **Patient (HI)**, or switch `/en` to `/hi`, `/ta`
    or `/ml` on any screen. Open the timeline.
    *Say:* the interface is translated, but clinical content such as
    "Type 2 diabetes mellitus" stays exactly as recorded, because
    translating it would invent a medical claim. Dates and numbers come
    from `Intl` with lakh grouping. Mention that Tamil and Malayalam
    are machine-translated and unreviewed.

## Fallbacks

- **No email in Mailpit:** run `docker compose logs backend | rg -i smtp`.
  Registration and email delivery are decoupled, so the account may exist
  anyway.
- **Every route but `/` returns 404:** the frontend image is stale. Run
  `docker compose up --build frontend`.
- **Local `next build` crashes on `/_global-error`:** the shell exports
  `NODE_ENV=development`. Use `NODE_ENV=production npm run build`.
