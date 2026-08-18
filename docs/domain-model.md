# Domain Model

How Pulse's entities are structured and why. Terms used here are defined in [`CONTEXT.md`](../CONTEXT.md); this document does not redefine them.

Supersedes `docs/archive/core_schema_rough.md`. Where the two disagree, this one is correct.

**Status:** in progress. Sections are filled in as the architecture tickets on [the map](https://github.com/moneytosms/Pulse/issues/1) resolve. Anything not yet covered is still an open ticket, not an omission.

---

## Identity and people

```
Role (1) ──< (N) User
User (0..1) ──── (1) Patient
User (0..1) ──── (1) Provider Staff
Provider (1) ──< (N) Provider Staff
```

**Patient is the aggregate root for everything clinical.** All medical data hangs beneath a Patient. There is no separate "Patient Record" entity — see [ADR-0002](./adr/0002-patient-is-the-aggregate-root.md).

**`patient.user_id` is nullable, and this is load-bearing.** A Provider can create a Patient for someone who has never registered — a walk-in whose lab report needs filing. That person later registers and *claims* the Patient, which links the User. An EHR that cannot hold data for an unregistered person is not an EHR, so this nullable column is a feature and must not be "fixed".

It also has a consequence for data quality: unclaimed Patients are the most likely source of duplicates. Two hospitals each create a Patient for the same walk-in, on different days, spelling the name differently.

---

## Medical entries

### Structure

One trunk table plus one table per kind — joined-table inheritance. See [ADR-0001](./adr/0001-medical-entry-joined-table-inheritance.md) for why, including why single-table and JSONB were rejected.

```
                    medical_entry
                         │
   ┌──────────┬──────────┼──────────┬──────────────┐
   │          │          │          │              │
diagnosis  prescription  lab_report  procedure  clinical_note
```

Each subtype table's primary key *is* a foreign key to `medical_entry.id`, cascading on delete. `medical_entry.entry_type` is the discriminator.

### The trunk

| Column | Notes |
|---|---|
| `id` | UUID, primary key |
| `patient_id` | FK → `patient.id`, indexed |
| `entry_type` | enum, polymorphic discriminator |
| `source_provider_id` | FK → `provider.id`, nullable — patient-uploaded entries have no Provider |
| `author_user_id` | FK → `user.id`, nullable — who entered it |
| `occurred_at` | when the clinical event happened |
| `recorded_at` | when it entered Pulse |
| `is_critical` | boolean |
| `superseded_by_id` | nullable self-FK — see corrections below |
| `metadata` | JSONB — see the rule below |

**Two timestamps, deliberately.** `occurred_at` is clinical time: when the blood was drawn, when the drug was prescribed. `recorded_at` is system time: when the row was inserted. They diverge constantly — a report uploaded three weeks after the test — and the timeline sorts by `occurred_at`, because that is the order the patient lived through.

### Subtypes

Fields per `CONTEXT.md`'s five kinds. Two details that are not obvious:

**Lab results need two value columns.** `value_numeric NUMERIC` and `value_text TEXT`, with `unit`, `reference_low` and `reference_high` alongside. Not every result is a number — cultures and serologies come back "Positive" / "Not detected". Analytics reads `value_numeric` and skips rows where it is null. The reference range is split into two numeric columns rather than stored as `"70-100"` text so that out-of-range flagging is a comparison, not a parse.

**Codes carry their system.** Every coded field is a `(code_system, code)` pair, with the human-readable name as the display field. Synthea seed data arrives as SNOMED-CT (conditions), LOINC (observations) and RxNorm (medications); Indian government reporting uses ICD-10. Storing a bare `code` would imply a vocabulary that was never stated. The pair keeps the seed data honest and leaves ICD-10 mapping possible without a migration.

### The JSONB rule

`medical_entry.metadata` holds **provenance only** — import batch id, source filename, external identifiers. Things stored and handed back whole.

**No clinical value ever goes in `metadata`.** Not "just this one field", not temporarily. The moment clinical data lands in JSONB it is unqueryable, untypeable and invisible to consent scoping, and the entire argument for typed subtype tables is undone. If a clinical field is missing, add a column.

### Corrections

Medical entries are **never updated in place and never deleted.** A correction inserts a new Medical Entry and sets `superseded_by_id` on the original.

- The timeline filters `superseded_by_id IS NULL`
- The full chain stays queryable, so "what did this say before it was corrected?" has an answer
- An audit story that permits silent `UPDATE`s on clinical data is not worth much

This replaces the unspecified "Version Information" field in the original rough schema.

### Indexes

| Index | Serves |
|---|---|
| `medical_entry (patient_id, occurred_at DESC)` | the patient timeline |
| `medical_entry (patient_id, entry_type, occurred_at DESC)` | type-filtered views |
| `lab_report (code_system, code)` | "show all HbA1c results" |
| `diagnosis (code_system, code)` | "show diabetes history" |
| `prescription (medication_name)` | "show current medications" |

### Reading entries

SQLAlchemy 2 maps this with `polymorphic_on` on the trunk and `polymorphic_identity` per subtype. Timeline reads use the `selectin_polymorphic` loader option, which emits one query for the trunk plus one per subtype *actually present in the result page* — flat, not N+1. A mixed 50-entry page costs at most six indexed queries regardless of page size.

`with_polymorphic` (a single LEFT JOIN across all five subtypes) is the alternative if it ever measures better. It is a loader option, not a schema change, so switching needs no migration.

---

## Documents

```
medical_entry (1) ──< (N) medical_document
```

The database stores metadata only: filename, MIME type, size, storage path, checksum, upload timestamp. Bytes live behind the storage adapter — currently the local filesystem on a mounted volume.

Pulse stores and serves documents. It never parses or interprets them; OCR is explicitly out of scope.

---

## Consent and access

```
patient (1) ──< (N) consent ──── (1) access_permission
```

**Consent** is the Patient's agreement. **Permission** is the live enforcement derived from it. They are separate tables because they answer different questions at different times, and because collapsing them destroys the audit trail.

### Consent

| Column | Notes |
|---|---|
| `patient_id` | who agreed |
| `grantee_user_id` | the Clinician granted access — an individual, never an organisation |
| `entry_types` | which kinds, or all |
| `from_date` / `to_date` | optional window over clinical dates |
| `purpose` | `TREATMENT`, `SECOND_OPINION`, `OTHER` + free text |
| `expires_at` | **mandatory** |
| `granted_at`, `revoked_at`, `revocation_reason` | lifecycle |

Consent rows are never deleted. Revoking stamps `revoked_at`; "did this patient ever agree to this?" must stay answerable.

**Grants are to individual Clinicians.** A patient can meaningfully agree that *Dr Meera Nair* may read their history. Nobody can meaningfully agree that *a hospital* may — that is four thousand people.

**Expiry is mandatory**, default 30 days, maximum one year, renewable. A consent that never expires is one nobody revisits.

**Entry-type scoping is supported; per-entry selection is not.** "Share my lab reports but not my clinical notes" is one array filter. "Tick nine of your two hundred entries" is a UI nobody completes.

### Who can read an entry

Five rules, in order; anything unmatched is denied.

1. The **Patient**, always, their whole history
2. The **authoring Provider's** staff — a hospital can read the report it filed
3. A **Clinician with live Consent** covering the entry
4. **Break-glass** — time-boxed, justified, loud
5. **Administrators: never.** See [ADR-0007](./adr/0007-administrators-cannot-read-clinical-data.md)

### Break-glass

Emergency access without consent. Requires a written clinical justification, expires after 60 minutes, writes a `CRITICAL` audit event, and notifies the Patient immediately. The answer to abuse is not prevention — it is that everyone knows within seconds.

### Enforcement

One query builder, `accessible_entries(actor, patient_id)`, applies rules 1-4 as SQL. Every read composes from it; no method returning entries takes less than an actor. See [ADR-0006](./adr/0006-consent-enforced-by-one-query-builder.md).

**No permission decision is cached anywhere.** Caching one for even sixty seconds makes immediate revocation false.

---

## Audit

```
user (1) ──< (N) audit_event
```

| Column | Notes |
|---|---|
| `id` | UUID |
| `actor_user_id` | nullable — a failed login has no authenticated actor |
| `actor_role` | **denormalised at write time** — roles change, history must not |
| `action` | closed enum |
| `resource_type`, `resource_id` | what was touched |
| `patient_id` | denormalised, nullable, indexed — "who accessed my records" is the hot query |
| `outcome` | `SUCCESS` \| `DENIED` |
| `occurred_at` | |
| `request_id` | joins the event to the request that caused it |
| `ip`, `user_agent` | |
| `metadata` | JSONB, constrained below |

**Append-only, enforced by grant** — the application role has `INSERT` and `SELECT` only. See [ADR-0008](./adr/0008-audit-log-is-append-only-by-grant.md).

**No clinical data in `metadata`. Ever.** Not a diagnosis name, not a lab value, not a note excerpt. Logging the contents of a viewed record would create a second copy of the medical record outside consent enforcement, readable by anyone who can read audit logs — undoing every access control in the project. Metadata holds identifiers, counts, entry types, and the break-glass justification.

This rule is also what makes [ADR-0007](./adr/0007-administrators-cannot-read-clinical-data.md) true: administrators can read the full audit log precisely because it contains no clinical content.

**Events are emitted explicitly in the service layer**, not via ORM hooks. The most important audit events are *reads*, and a read produces no database write for a hook to fire on — `ENTRY_VIEWED` would have been invisible. The read path is narrow because every read composes from `accessible_entries`, so coverage is tractable.

**One event per access, not per row.** A clinician opening a 50-entry timeline produces one `ENTRY_VIEWED` describing the query. Otherwise the audit table outgrows the clinical data it describes and the patient's access view becomes unreadable.

Patients see a filtered projection: clinician name and provider, action, timestamp, entry type. Never identifiers, never other patients' events, never system-internal actions.

---

## Analytics

**There is no `summary_insight` table.** Analytics are computed on read, through `accessible_entries`. See [ADR-0009](./adr/0009-analytics-computed-on-read.md).

Series for v1: lab trends per test code, vital sign trends, visit frequency by month, active medications over time, and provider upload counts.

Abnormality flagging compares a value against `reference_low` / `reference_high` **on its own row**, not against a central reference table — ranges are lab-specific and assay-specific, and a shared table would produce confidently wrong flags on historical data.

Medication adherence is excluded. It is not derivable from prescriptions: knowing a drug was prescribed says nothing about whether it was taken.

---

## Notifications

```
user (1) ──< (N) notification
user (1) ──< (N) notification_preference
```

`notification` stores `type` + `params` (JSONB), **never rendered text**. The body is rendered at read time through the locale catalogs — a notification stored as English is untranslatable forever, and notifications are read weeks after they are written.

`params` holds identifiers and non-clinical values only. Same rule as audit metadata, same reason: a notification is a copy of information sitting outside the consent filter.

Preferences are per event type per channel. Mandatory events — break-glass, consent changes, security — are absent from the preferences UI rather than shown as locked toggles.

**"A clinician viewed your records" is a daily digest, not a per-view notification.** Per-view it fires every time a doctor opens a timeline, which trains users to ignore the notification stream entirely — worse than no transparency feature, because it looks like one. With no scheduler in the stack, the digest is computed on read.

---

## Data quality

```
patient (1) ──< (N) data_quality_flag
duplicate_review_item ──── two patient ids
patient_merge ──── audit trail of a completed merge
```

### Duplicate detection

Deduplication is over **Patient identities**, not entries. The realistic case is two Providers each creating an unclaimed Patient for the same walk-in.

Scoring uses `pg_trgm`: trigram similarity on a normalised name (0.5), date of birth with transposition tolerance (0.3), phone (0.2).

**Name normalisation sorts tokens.** Indian naming conventions place the given name first in some regions and last in others, so "Menon Ramesh" and "Ramesh Menon" are the same person and must not score as unrelated.

**Trigram, not phonetic.** Soundex and Metaphone encode English phonetics and perform poorly on romanised Indian names. The actual failure mode is transliteration variance, which trigrams handle and which is indexable.

Candidates are **blocked** before scoring — same birth year, same phone, or a trigram index hit — or detection is O(n²) and degrades with every patient added.

### Merging

Human-only, reversible, tombstoned. See [ADR-0011](./adr/0011-merges-are-human-only-and-reversible.md). The review interface shows identity fields and entry counts, never clinical contents.

### Flags

`MISSING_DOB` · `MISSING_CONTACT` · `FUTURE_DATED_ENTRY` · `IMPLAUSIBLE_DOB` · `UNCLAIMED_LONG_LIVED`

Informational. They never block anything.

What is already fixed:

- Consent and Permission are separate entities. Consent records that the Patient agreed; Permission is the live enforcement derived from it.
- Audit Events are append-only — never updated, never deleted.
- Summary Insights are derived data. A clinical fact never originates in analytics.
- Merges are always human-initiated. Nothing auto-merges two Patients.
