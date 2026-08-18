---
status: accepted
---

# Medical Entry uses joined-table inheritance

Pulse's five kinds of clinical event — Diagnosis, Prescription, Lab Report, Procedure, Clinical Note — share about eight fields and diverge in roughly twenty-five more. We map them as one `medical_entry` trunk table plus one table per kind, each keyed on the trunk's primary key, using SQLAlchemy's `polymorphic_on` / `polymorphic_identity`.

## Considered options

**Single-table inheritance** — one wide table with nullable columns for every kind. Rejected: the five kinds share almost no fields, so this means ~25 nullable columns where any row uses five, and no database-level guarantee that a row typed `diagnosis` actually carries a diagnosis code. Recovering that guarantee needs per-type `CHECK` constraints, which is more SQL than the joined schema costs and reads worse.

**JSONB payload** — typed trunk, subtype fields in a JSONB column. Rejected on analytics: lab results are what the trend charts plot, which needs numeric comparison, ordering and aggregation on `value_numeric`. In JSONB each of those is a cast, casts are awkward to index well, and nothing prevents a write putting `"120/80"` where a number belongs. The failure is silent until a chart renders wrong.

## Consequences

The obvious objection to joined tables is join fan-out on the patient timeline, which reads all kinds at once. In practice `selectin_polymorphic` issues one query for the trunk plus one per kind present in the page — at most six indexed queries for a 50-entry page, flat in page size. `with_polymorphic` (single LEFT JOIN across all five) remains available as a loader option if it ever measures better; switching needs no migration.

Three sub-decisions follow from this one and are recorded in `docs/domain-model.md`: `metadata` JSONB is restricted to provenance and never holds clinical values; lab results carry both `value_numeric` and `value_text` with a split numeric reference range; corrections supersede via `superseded_by_id` rather than updating rows in place.
