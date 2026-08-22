# Frontend Rules

Next.js App Router + TypeScript + Tailwind + Radix UI + next-intl. Applies to `frontend/`.

## i18n

- The `next-intl` middleware matcher **must exclude `/api`**. Caddy routes those to FastAPI on the same origin, and a locale middleware rewriting API paths breaks every request in a way that takes an hour to find.
- Catalogs are one file per feature per locale, so four people editing translations do not conflict on every PR.
- Never render `error.message` from an API response. Render from `error.code` — that is the only reason four locales are possible.
- Missing keys throw in development and CI, and fall back to English only in production. A silent fallback means a missing Tamil string is found by a reviewer who reads Tamil, live.
- Numbers and dates come from `Intl` — `Intl.NumberFormat('en-IN')` gives lakh grouping, dates render day-first. Do not hand-write formatting; the platform's output is better than ours.
- Fonts must carry Devanagari, Tamil and Malayalam. Most default UI stacks carry none of the three and fail silently to whatever the OS has.
- **Clinical content is never translated** — medication names, test names, diagnoses and note text render as recorded, in every locale.

## Structure

- Patient portal is mobile-first: mid-range Android, patchy connectivity, older users on cheap screens. Clinician, provider and admin portals are desktop-first and data-dense. A design pretending these are the same product fits neither.
- Wrap Radix primitives once, in the shared component directory, before the second screen needs them. The same button must not be built four times.
- Colour never carries meaning alone — critical results, consent state and audit severity each need an icon or a label alongside the colour.

## Working against the backend

- Build against `@stub` endpoints. If a screen is blocked on a finished backend service, say so immediately — the stub was skipped and that is a process bug, not something to wait out.
- TypeScript types for the API are generated from OpenAPI. Never hand-maintain a type that mirrors a Pydantic schema, and never hand-maintain the error-code union.
