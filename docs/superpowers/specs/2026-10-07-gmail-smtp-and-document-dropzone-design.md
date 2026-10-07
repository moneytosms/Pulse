# Gmail SMTP and document dropzone

**Status:** implemented; live Gmail delivery awaits local App Password setup.

## Context

Pulse currently routes verification and notification email to Mailpit on the
Compose network. The SMTP adapters support only host and port, without SMTP
authentication or TLS. The new-entry form accepts one optional PDF, PNG, or
JPEG using the browser's plain file input and reports upload progress after
entry creation.

## Goals

1. Send Pulse verification and notification email through the user's personal
   Gmail account in local Compose and hosted deployments.
2. Keep automated tests isolated from real email delivery.
3. Replace the plain document chooser with an accessible drag-and-drop control
   while preserving the current single-file entry submission flow.

## Email design

- Add shared SMTP configuration for host, port, username, password, STARTTLS,
  SSL, sender address, and public application URL.
- Use `smtp.gmail.com`, port `587`, STARTTLS, and the full Gmail address as the
  username for the selected Gmail configuration. Authentication uses a Google
  App Password when available; the ordinary Google account password is never
  used. App passwords are supplied through environment secrets and are never
  committed.
- Keep Mailpit as the no-credentials local fallback so a fresh clone remains
  runnable. When local `.env` SMTP values are supplied, Compose sends through
  Gmail. Hosted deployments receive the same settings through their secret
  configuration. The sender address and credentials are not hard-coded.
- Keep the test dependency overrides on `FakeIdentityProvider` and
  `FakeNotificationProvider`; CI must not send external email.
- Set `PUBLIC_BASE_URL` to the HTTPS address recipients can open. A local
  `localhost` URL is only usable on the developer's own machine; local email
  sent to another person requires a public HTTPS tunnel or hosted address.
- Centralize SMTP delivery so verification and notification email use the
  same TLS and authentication behavior. SMTP failures continue through the
  existing request error path; adding a queue or retry service is out of scope.

Google references: [Gmail SMTP settings](https://support.google.com/a/answer/176600)
and [Google App Password requirements](https://support.google.com/accounts/answer/185833).

## Upload control design

- Replace the native-looking chooser with a dropzone that accepts drag and drop
  and has a visible keyboard-accessible browse button backed by a file input.
- Preserve one optional file per new entry. Selecting or dropping a new file
  replaces the current selection; a remove action clears it.
- Accept PDF, PNG, and JPEG in the chooser and drop handler. The backend
  remains authoritative for content and size validation.
- Show the selected filename and size, a clear remove/replace affordance, and
  the existing upload progress. Announce selection and upload status to screen
  readers; preserve visible focus and reduced-motion behavior.
- Add localized strings to the existing English, Hindi, Tamil, and Malayalam
  entry catalogs. Keep clinical content untranslated. The locale review status
  remains as recorded in `docs/locale-review.md`.
- Do not change the records API, document model, accepted file types, or
  multiple-file behavior in this task.

## Verification

- Add focused backend coverage for SMTP configuration and TLS/authentication
  without connecting to Gmail.
- Add frontend coverage for keyboard browse, drag/drop selection, remove or
  replacement, rejected file types, and progress rendering.
- Run the relevant backend and frontend checks after implementation. A live
  Gmail delivery check is a separate manual verification requiring the user's
  locally configured App Password and a reachable verification URL.

## Out of scope

- Gmail API OAuth, bulk email, retry queues, provider dashboards, and email
  deliverability operations.
- Multiple document selection/upload in one entry form submission.
- Changes to clinical record authorization or document storage durability.
