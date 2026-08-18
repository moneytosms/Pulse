---
status: accepted
---

# Route authorization is default-deny, enforced by a coverage test

Every API route must declare either a required permission or an explicit public marker. A test enumerates the application's routes and fails CI if any route declares neither.

## Why

A centralised `PermissionService` only helps if it is called. The realistic failure in a nine-module system built by four people under deadline is not a wrong permission check — it is a **missing** one, on an endpoint added at 2am, which then silently returns other people's medical records.

Conventions do not catch that. Code review sometimes catches it. A red CI check always catches it, costs about twenty lines, and catches it on the day the endpoint is written rather than during a demo.

## Consequences

The test must exist before the modules are built. Retrofitting it against sixty endpoints means sixty simultaneous decisions and a strong temptation to mark things public to get CI green; introduced against three endpoints it is free and stays free.

Role permissions are necessary and never sufficient — they answer "may a Clinician read records", not "may this Clinician read *this* Patient's records". The latter is consent-based row filtering in the repository layer and is a separate mechanism.
