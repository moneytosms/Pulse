---
status: accepted
---

# Caddy puts the frontend and API on one origin

A single Caddy reverse proxy sits in front of the Compose stack. It routes `/api/*` to FastAPI and everything else to Next.js. Both are served from the same origin, in every environment — a developer's laptop included.

This is recorded because it looks like infrastructure plumbing rather than a decision, and because the alternative is the default outcome if nobody chooses this deliberately: Next.js on one port, FastAPI on another, and a CORS configuration written to paper over it.

## Why

Sessions are an `HttpOnly` cookie holding an opaque token (ADR-0003). Cookie authentication across two origins forces `SameSite=None`, which forces `Secure`, which forces HTTPS in local development, and every request becomes a CORS preflight. None of that is hard individually. Together they are a category of bug that only appears when the deployment topology differs from the developer's own machine — a missing header on the demo laptop, a preflight that behaves differently on the grading server.

Same-origin deletes the category rather than defending against it. Six lines of Caddy config route by path prefix, cookies are first-party by construction, and there is no cross-origin request to configure CORS for in the first place. Given a four-person team on a two-month timeline with a graded live demo, "nothing to get wrong" beats "correctly configured" every time the person configuring it is not the person debugging it under pressure.

## Consequences

Caddy is now in the request path for local development, not just anything resembling production — one more container in `docker compose up`, and one more place a misrouted request can hide.

The locale middleware (`next-intl`, path-prefixed routing) must explicitly exclude `/api` from its matcher. If the frontend's own middleware rewrites API paths looking for a locale prefix first, every API call breaks in a way that costs real time to trace back to a matcher config rather than the request path. This is a live trap, not a hypothetical one — see the i18n section of `architecture.md`.

Because same-origin is what makes first-party cookies work at all, this decision and ADR-0003 stand or fall together: reopening one reopens the other.
