---
status: accepted
---

# Analytics are computed on read; there is no Summary Insight table

Trends, counts and averages are computed per request from Medical Entries, through the same consent filter as any other read. The `summary_insight` entity from the original rough schema is dropped rather than left empty.

## Why

**A stored insight has no actor.** Who may see a trend depends entirely on who is asking — a Clinician with consent scoped to lab reports must not see a trend computed over clinical notes. A materialised row is computed once, without an actor, so it is either unfiltered (a leak waiting to be served) or recomputed per actor, which is computing on read with extra bookkeeping.

**There is no scheduler.** Nothing in the stack runs in the background, so a materialised insight would have to be refreshed inside the request that wrote the entry — making uploads slower in order to make charts faster.

**The queries are not slow.** A patient's lab series for one test code is tens of rows against an existing index.

## Consequences

Analytics queries must compose from `accessible_entries` (ADR-0006). Aggregation is the easiest way to leak what is being aggregated — a count reveals existence, a trend reveals values.

If a chart ever measures slow, the answer is a Postgres materialised view with an explicit refresh. Not Redis (ADR-0005).

Medication adherence, listed in the original schema, is excluded: it is not derivable from prescription data. Knowing a drug was prescribed says nothing about whether it was taken, and computing it anyway would be inventing a clinical claim.
