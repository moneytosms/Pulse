---
status: accepted
---

# Seed data is Synthea output with a deterministic Indian identity overlay, committed to the repo

Clinical content comes from Synthea, a synthetic patient generator that emits longitudinal records with real coded vocabularies — SNOMED-CT for conditions, LOINC for observations, RxNorm for medications. A deterministic overlay then replaces its American names, addresses and phone numbers with Indian ones. A known set of near-duplicate Patient pairs is planted on top — transliteration variants, typo'd dates of birth, initials versus expanded names — alongside deliberate near-miss pairs that are genuinely different people who merely look similar. The whole transformed dataset is committed to the repository rather than regenerated on setup.

**No real patient data ever enters this system.** Every Patient, Medical Entry and Medical Document Pulse holds is synthetic, generated or overlaid by this pipeline. That is stated here because this is the ADR that governs where data comes from.

## Why

Hand-writing plausible clinical histories does not scale past a handful of patients and produces data too clean to be useful — every value in range, no ground truth to test duplicate detection against. Synthea generates hundreds of longitudinal patients in seconds and, more importantly, generates them with real coded vocabularies: the `(code_system, code)` pairs that keep entries honest and the analytics that plot lab trends are only as credible as the codes underneath them.

But Synthea's identity layer is American, and an application built for an Indian demographic showing "Michael Johnson, 4521 Oak Street" in every demo would undercut the premise in front of anyone watching. The overlay fixes exactly that, without touching the clinical rows that make the data useful in the first place.

Committing the generated dataset rather than regenerating it on setup is a project-constraint call: Synthea is a Java tool, and requiring a JDK on every teammate's machine before anyone sees a working system contradicts the actual acceptance test — `git clone && docker compose up`. The generator and overlay scripts stay in the repo and stay runnable for when the schema changes; they are just not on the critical path for a fresh clone.

## Consequences

The committed dataset is a binary-ish artifact in git history — megabytes of CSV a normal diff review will not meaningfully inspect.

Regeneration must be pinned to a fixed Synthea version and a fixed seed (patient-generating and clinician-generating are separate seeds), or "regenerate the dataset" silently produces a different one. The overlay must be equally deterministic, for the same reason: a bug report against seed data has to be reproducible on every teammate's machine.

Planting only true duplicate pairs would tune the detection heuristic to say yes to anything similar, with no way to see its false-positive rate before it runs against real-looking data. The deliberate near-misses are what make precision measurable rather than merely demonstrable. Whatever the heuristic flags still only ever produces a review item — ADR-0011 governs what happens next, and a planted pair is exactly the confident-looking match an auto-merge would act on, which that ADR argues against.
