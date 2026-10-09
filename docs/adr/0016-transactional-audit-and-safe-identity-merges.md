---
status: accepted
---

# Clinical operations own their transaction and identity merges have explicit limits

The modular monolith remains the deployment and ownership boundary. An outer business operation commits its mutation, audit event and required in-app notification together. Audit and notification helpers flush and never commit another service's pending state. Clinical reads commit their audit event before returning data; an audit failure fails the read. SMTP delivery through the configured adapter runs after the request commits and remains best effort for the synthetic demo. Guaranteed external delivery would require a durable outbox.

## Live clinical access

Clinical SQL composes from `accessible_entries`. The consent module exposes a narrow composable predicate, rather than allowing records to query foreign table names. Consent and emergency grants use correlated EXISTS and `statement_timestamp()` expiry checks. Under PostgreSQL READ COMMITTED, a statement starting after committed revocation denies access. An already-running statement or data already returned cannot be withdrawn. There is no permission cache.

Provider identity comes from authenticated staff membership. Mismatched client attribution and staff without a provider are rejected. Corrections and document attachment require the original entry to belong to that provider. Identity lookup additionally requires an authored entry or owner/live-clinician relationship. Admins retain identity/count access only.

Raw SQL in domain modules is prohibited by CI; owned ORM models and explicitly published service query seams are allowed. Identity/email projections and admin entry counts are batched. Existing service-returned ORM identities remain typed, internal implementation objects; they are not HTTP contracts.

## Supported merges and reversals

An administrator chooses a surviving identity. The loser must be unclaimed, have no live consent/emergency grants, and neither identity may be tombstoned or participating in another unreversed merge. A claimed winner and unclaimed loser, or two unclaimed identities, are supported. Two claimed accounts require a future account-reconciliation workflow. No linked account or consent grant is silently transferred.

Merge, entry creation/correction, document attachment and grant creation lock affected patient rows. Multi-patient locks use stable UUID order. Concurrent opposite merges cannot form a cycle. A merge records the exact moved entry IDs and database operation time. Original immutable audit rows keep their original patient ID; the surviving patient's current audit scope includes those tombstoned identities. Reversal removes that scope without rewriting audit history.

Automatic reversal is conditional: all moved entries must still belong to the winner, supersession links must remain within the original moved set, and no document may have been attached to a moved entry after the merge. Pre-existing revision chains remain reversible. Later corrections/documents or dependent merges return coded 409 for manual review. Reversal is never a blind reassignment. This qualifies the unconditional reversibility wording of ADR-0011.

## Operation-to-audit matrix

| Operation | Event |
|---|---|
| Timeline / entry detail | ENTRY_VIEWED, once per operation |
| Document download | DOCUMENT_VIEWED, only after bytes pass integrity checks |
| Clinical analytics / quality flags | ANALYTICS_VIEWED |
| Entry creation / replacement correction | ENTRY_CREATED / ENTRY_CORRECTED |
| Document upload | DOCUMENT_UPLOADED |
| Consent grant / withdrawal | CONSENT_GRANTED / CONSENT_REVOKED |
| Emergency grant | BREAK_GLASS_ACCESS |
| Clinical lookup denied or absent | ACCESS_DENIED, opaque resource ID, no patient FK |
| Login success / failure | LOGIN_SUCCESS / LOGIN_FAILURE |
| Password reverification | STEP_UP_SUCCESS / STEP_UP_FAILURE |
| End session / all sessions | LOGOUT / LOGOUT_ALL |
| Merge / reversal | PATIENT_MERGED / MERGE_REVERSED |

Unauthenticated failures have null actor identity/role. Events capture request ID, peer IP and bounded user agent. Audit metadata is a closed set; notification params accept typed identifiers/counts and reject extra fields. Passwords and clinical values are never logged in unhandled-error responses or notification params. Authentication's Redis/PostgreSQL writes cannot share one transaction: failed login auditing destroys any newly minted session, and logout always removes access before recording success.

## Bounded collections and contracts

Persisted timeline, consent, audit, notification, duplicate-review and merge lists use keyset pages with a maximum of 100 rows. Computed chart arrays retain their array contract with optional inclusive UTC `fromDate` / `toDate` bounds and a hard 5,000-result-row ceiling. Overflow returns ANALYTICS_WINDOW_TOO_LARGE rather than silently truncating a clinical series. This is the bounded exception to universal cursor pagination for computed charts.

OpenAPI is the source for generated TypeScript DTOs and enum values. CI regenerates in check mode and verifies locale key/interpolation parity and enum coverage. Notification titles/bodies render from localized type/params. Optional delivery preferences expose supported in-app delivery only. DAILY_DIGEST remains the stable enum code for activity since the patient's last check, not a scheduled daily summary.

Digest checks serialize on the patient row and compare total committed view events with counts already represented in digest history. A transaction committing late is included on the next check even if its event timestamp predates the previous digest; timestamps are not used as consumption watermarks.
