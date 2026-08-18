---
status: accepted
---

# Patient is the aggregate root; there is no Patient Record entity

The original rough schema modelled `Patient (1) —— (1) Patient Record`, with Patient Record as the aggregate root owning all clinical data. We collapsed the two: **Patient is the aggregate root**, and medical entries, data quality flags and duplicate review items reference `patient.id` directly.

This is recorded because the earlier design said the opposite, and because "shouldn't the medical record be its own entity?" is a reasonable question someone will ask again.

## Why

A strict 1:1 with no independent lifecycle is an empty layer — it costs a join on every read, forever, and gives the same concept two names. Two things could have justified it, and neither survived:

**Records existing before an account** is a real requirement — a hospital files a lab report for a walk-in who has never registered. But this is already handled one layer up, because `User (0..1) —— (1) Patient` is itself optional: an unregistered person is a Patient row with a null `user_id`. Patient Record added nothing.

**Merging duplicates** is also real, but merging means repointing the loser's entries at the surviving Patient and tombstoning it. A 1:1 table in the middle adds a second row to repoint and a second identity to reason about, and makes none of it easier.

The DDD instinct behind the original design was right — all clinical data should hang beneath one owning entity with a single source of truth. The only error was assuming that entity is distinct from the Patient.

## Consequences

`patient.user_id` is nullable and load-bearing; it is what makes the provider upload portal work for unregistered people, and it must not be "tidied up" into a required column.

It also implies where duplicates come from: two Providers each creating an unclaimed Patient for the same walk-in, spelling the name differently. Detection heuristics and planted seed duplicates should target that scenario rather than double-signup.
