# Clinical Safety and Access Rules

These are the rules the project is graded on and the ones that are expensive to discover late. They apply everywhere, in every layer. Breaking one is not a style disagreement.

## Access

- Every read of clinical data composes from `accessible_entries(actor, patient_id)` — never `select(MedicalEntry)` directly. CI lints for this.
- No function returning Medical Entries takes less than an actor. If a signature has no actor, the access rules have nowhere to apply.
- Consent-denied reads return **404, never 403**. A 403 confirms the record exists, which reveals that a person is a patient at all.
- Never cache a permission decision — not for sixty seconds, not "just for the timeline". Caching one makes immediate revocation a lie, and immediate revocation is the project's central promise.
- Administrators can read no clinical data, on any endpoint, ever (ADR-0007).
- Every route declares a required permission or an explicit public marker. There is no third option; CI fails on undeclared routes (ADR-0004).

## Clinical data

- Medical Entries are never updated in place and never deleted. A correction inserts a new Entry and stamps `superseded_by_id` on the original.
- **No clinical value goes in JSONB.** `medical_entry.metadata` is provenance only — import batch, source filename, external identifiers. Not "just this one field", not temporarily. If a clinical field is missing, add a column.
- **No clinical data in audit metadata. Ever.** Not a diagnosis name, not a lab value, not a note excerpt. Logging viewed contents creates a second copy of the medical record outside consent enforcement — it undoes every access control in the project, and it is what makes administrator access to the audit log safe.
- **No clinical data in notification params.** Same rule, same reason: a notification is a copy of information sitting outside the consent filter.
- Clinical content is never translated. A Diagnosis recorded as "Type 2 diabetes mellitus" reads that way in every locale — translating it would be inventing a medical claim.

## Audit

- Audit Events are emitted explicitly in the service layer, never via ORM hooks. The most important events are *reads*, and a read produces no write for a hook to fire on.
- One event per access, not per row. A 50-entry timeline is one `ENTRY_VIEWED` describing the query.
- `actor_role` is denormalised at write time. Roles change; history must not.
- The audit table is append-only by database `GRANT`, not by convention. The application role holds `INSERT` and `SELECT` only.

## Data

- Pulse never holds real patient data. Seed data is synthetic, and identity fields (names, phones, addresses) are generated, never sourced from a real person.
- `patient.user_id` is nullable and load-bearing — it is how a Provider files records for someone who has never registered. It is not a bug to be fixed.

## When one of these gets in the way

That is the rule working. Escalate to the map rather than working around it — every one of these was decided against a named alternative, and the reasoning is in `docs/adr/`.
