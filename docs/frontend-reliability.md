# Frontend reliability

The frontend functional review identified thirteen gaps in clinical presentation,
recovery, navigation, and asynchronous state. The fixes retain the existing
role-specific screens and server-authoritative access checks.

| Finding | Resulting behavior |
|---|---|
| Qualitative results plotted as zero | Non-numeric results remain recorded text in a readable results table; actual numeric zero is preserved. |
| Units omitted from trends | Numeric charts are partitioned by the recorded unit; the table includes units and reference ranges. |
| Critical flag omitted from detail | Patient and clinician detail screens show an icon and localized Critical label. |
| Superseded status omitted from history | Old entries identify their replacement; replacement entries link back to the previous version. |
| Locale navigation discarded query context | Locale changes preserve the full query string, repeated keys, and fragment. Entry/consent drafts and pending attachments require a discard decision. |
| Logout errors ignored | A failed logout stays visible with retry; success or an already expired session navigates to sign-in. |
| Verification recovery dead end | Resend accepts an email when none is known; temporary verification errors offer retry. Locale remounts reuse the one-use token outcome rather than submitting it again. |
| Attachment partial failure | Saving an entry and uploading its document are distinct states. Progress remains visible; replacement/retry uses the saved entry ID. Verified staff can also attach a document from its current detail view. |
| Stale pagination responses | Pending continuation requests are cancelled when the query changes or the screen unmounts; aborted results and errors are ignored. |
| Emergency banner searched only five events | The banner requests the latest emergency event within the last 72 hours using the patient-scoped audit projection. |
| Clinician discovery ignored continuation | Consented-patient discovery retains its cursor, loads additional patients, and offers recovery. |
| Initial patient lookup could not be retried | Timeline, audit, consent, profile, and analytics can retry initial lookup failures. |
| Translated tablet navigation overflow | The compact navigation remains until the xl breakpoint, keeping account controls reachable. |

`GET /api/v1/audit-events` accepts optional `action` and `since` query parameters.
`since` requires a timezone-aware timestamp. Filters are applied before cursor
pagination and keep the caller's live patient identity scope; requesting another
patient's audit history still returns 404. No schema migration is required.

Clinical values and units remain untranslated. Charts never normalize values or
convert units, and the results table is available independently of the chart.
Clinical drafts are not persisted in browser storage. Permission decisions remain
on the server on every protected request.

Regression coverage lives in `frontend/e2e/frontend-reliability.spec.ts`, alongside
the existing browser suite. Tests cover delayed requests, partial uploads without
a duplicate entry POST, logout failure, verification recovery, null versus zero,
unit separation, critical/superseded details, all four locales at phone/tablet/
desktop widths, and mobile keyboard/theme behavior. Real PostgreSQL tests in
`backend/tests/test_audit_events.py` cover the new audit filters, recent events
behind routine activity, foreign-patient denial, and naive timestamp rejection.

Request cleanup follows [React's effect cleanup semantics](https://react.dev/reference/react/useEffect)
and [AbortController](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort).
Locale navigation uses the [next-intl navigation API](https://next-intl.dev/docs/routing/navigation).

These changes do not implement a patient directory, profile editing, password
reset, or provider onboarding. Those are separate product capabilities, rather
than failures in the reviewed workflows.

## Follow-up entry safety checks

The entry form retains drafts when switching types, but sends only the selected
subtype's fields. An unfinished lab reference range cannot invalidate a clinical
note, and hidden medication/note values do not enter another subtype's payload.
Optional prescription coding is visible and preserved when correcting an
imported prescription. All entry controls are disabled during save and restored
with their draft intact after a failed request.

Clinician/provider detail also verifies that the returned entry belongs to the
patient in the route. A mismatch uses the same not-found presentation and exposes
neither the entry nor correction/attachment controls. Both route identifiers
participate in loading cleanup; UUID comparison accepts letter-case differences.
This UI consistency check complements the existing server authorization.

Four additional browser regressions cover subtype switching, in-flight save
locking and recovery, patient-route mismatch, and coded prescription corrections.
Form grouping follows the native
[`fieldset` disabled behavior](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/fieldset).
