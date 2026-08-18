---
status: accepted
---

# Administrators cannot read clinical data

The `ADMINISTRATOR` role manages users, roles, providers and the duplicate review queue. It grants no access to Medical Entries or Medical Documents whatsoever.

## Why

The default instinct is that admin means superuser. That instinct is how real health systems end up with hundreds of staff able to read a celebrity's file, and it makes the consent model decorative — if any administrator can read anything, patient consent governs only the people who were never the risk.

Nothing an administrator legitimately does requires clinical content. The hardest case is duplicate resolution, and it resolves cleanly: deciding whether two Patients are the same person needs identity fields — name, date of birth, phone, address — and entry counts. Never the entries themselves.

## Consequences

Consent grants are to Clinicians only. There is no administrative override; the emergency path is break-glass, which is clinician-invoked, time-boxed, justified and immediately visible to the patient.

The duplicate review interface must be built against identity fields and counts, which constrains its design (#12).
