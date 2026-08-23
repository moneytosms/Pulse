---
status: accepted
---

# The API returns error codes, never user-facing strings

Every non-2xx response carries the same envelope:

```json
{
  "error": {
    "code": "CONSENT_ALREADY_REVOKED",
    "message": "This consent has already been revoked.",
    "details": [{ "field": "entryTypes", "code": "INVALID_ENTRY_TYPE" }],
    "requestId": "01J…"
  }
}
```

`code` is `SCREAMING_SNAKE_CASE`, drawn from a single Python enum, and is the only field the frontend ever renders text from. `message` is an English default for logs and developers — it is never shown to a user. FastAPI's default `{"detail": ...}` handling is replaced globally, including for `RequestValidationError`, so validation failures do not become the one response shape that breaks the rule. Stored notifications follow the same split: type plus parameters in the database, rendered to text only at read time.

## Why

Pulse ships in English, Hindi, Tamil and Malayalam. That is the whole argument. A raw English string in a response body — `"This consent has already been revoked."` returned as the thing to display — is untranslatable forever without touching every endpoint that produces one, and nobody retrofits that across nine modules once the deadline is a week away. Codes are translatable from day one because the string lives in a locale catalog on the frontend, keyed by `code`; adding a language means adding catalog entries, not touching a backend route.

This is the genuine one-way door on this list, not merely an expensive-to-reverse choice. A codebase where half the endpoints return renderable messages and half return codes cannot be fixed incrementally — it has to be fixed everywhere at once, which is exactly the work this ADR avoids by deciding it before the modules are written.

## Consequences

Codes are a permanent contract. Once shipped, a code is never reworded — a rename is indistinguishable from a new code to anything already deployed, and "just tidy up the enum" is the mistake this decision exists to prevent.

The enum is exported through OpenAPI and generated into a TypeScript union at build time, so neither side hand-maintains a duplicate list that can drift. An unrecognised code falls back to a generic localized message rather than rendering blank.

`message` still has to be written well — it is what shows up in logs when a teammate is debugging a failure at 1am. It just never reaches a Patient, a Clinician, or Provider Staff.
