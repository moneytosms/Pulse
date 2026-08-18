---
status: accepted
---

# The audit log is append-only by database grant, not by convention

The application's database role holds `INSERT` and `SELECT` on `audit_event` and nothing else. No `UPDATE`, no `DELETE`. Migrations run as a separate owner role.

## Why

Immutability is the property the project's compliance story rests on, and "we simply don't update that table" is not a property — it is an intention that survives until someone writes a cleanup script.

The grant is one line in a migration and converts the intention into something the database refuses to violate. It also matches the real threat model: an audit log's job is to remain trustworthy when the application is compromised, and an application that can delete its own audit rows can erase its own tracks.

## Consequences

Two database roles must exist from the first migration. Adding this later means revisiting the migration setup after nine modules already write freely.

Corrections to audit data are impossible by design. If an event is written wrong, the fix is a new event, not an edit.
