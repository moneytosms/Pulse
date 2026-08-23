# Database Rules

PostgreSQL + SQLAlchemy 2 + Alembic. Applies to `backend/app/db/`, every module's `models.py` and `repository.py`, and `seed/`.

- All SQL lives in `repository.py`. No queries in services, no queries in routes.
- Every schema change is an Alembic migration. Never edit a migration that has been applied in any environment — add a new one.
- Two database roles from the first migration: the application role holds `INSERT`/`SELECT` only on `audit_event`. Append-only is enforced by `GRANT`, not by convention (ADR-0008).
- Medical entries use joined-table inheritance — one `medical_entry` trunk, one table per kind, subtype primary key *is* a foreign key to the trunk, cascading on delete (ADR-0001).
- Timeline reads use `selectin_polymorphic`, which emits one query per subtype present in the page rather than one per row. The N+1 everyone expects from this pattern does not occur.
- Index every foreign key. The five indexes the domain model names are load-bearing for the timeline, not optional tuning.
- Coded clinical fields are always a `(code_system, code)` pair plus a display name. A bare `code` implies a vocabulary nobody stated.
- Lab results carry `value_numeric` **and** `value_text`. Not every result is a number — cultures come back "Positive". Reference ranges are two numeric columns, never a `"70-100"` string, so out-of-range flagging is a comparison and not a parse.
- Redis is never a source of truth (ADR-0005). Sessions, rate-limit counters, short-lived verification challenges — all TTL'd, all reconstructible. If Redis is wiped, users log in again and nothing else breaks.
- Duplicate detection blocks candidates before scoring — same birth year, same phone, or a trigram index hit. Unblocked scoring is O(n²) and degrades with every Patient added.
- Name normalisation for duplicate scoring **sorts tokens**: Indian naming order varies by region, so "Menon Ramesh" and "Ramesh Menon" must not score as unrelated. Trigram, never Soundex or Metaphone — those encode English phonetics and fail on romanised Indian names.
- Seed data is committed, deterministic, and generated from a pinned Synthea version and seed. Planted duplicates *and* planted near-miss non-duplicates, so detection precision is measurable rather than merely demonstrable (ADR-0015).
