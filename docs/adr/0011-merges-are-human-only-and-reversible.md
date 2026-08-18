---
status: accepted
---

# Patient merges are human-initiated and reversible

Duplicate detection only ever creates a review item. Nothing auto-merges at any confidence score. Every merge records enough state to be undone.

## Why

Merging is the only destructive operation in Pulse and it operates on medical records. A wrong merge attaches one person's allergies, blood type and medication list to another person, silently, and the error surfaces later as a clinical decision made on someone else's data.

The cost asymmetry settles both halves. A missed duplicate is an inconvenience — two records that should be one. A wrong merge is a patient-safety incident. No similarity score justifies crossing that gap automatically, and a mistaken human click should not be permanent either.

Reversibility costs a `patient_merge` row storing the pair, the actor, and the ids of every row moved. That converts a catastrophe into an inconvenience.

## Consequences

The losing Patient is tombstoned with `merged_into_id`, never deleted — audit events referencing it must stay resolvable.

The review interface shows identity fields and entry counts only, never clinical contents, so that Administrators can work the queue without contradicting ADR-0007.

A pair marked `NOT_DUPLICATE` is recorded as such and never re-flagged.
