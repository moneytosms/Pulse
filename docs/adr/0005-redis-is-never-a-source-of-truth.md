---
status: accepted
---

# Redis holds sessions, rate limits and short-lived tokens — never a source of truth

Redis stores exactly three things: session records, rate-limit counters, and short-lived verification challenges. Everything has a TTL. If Redis is wiped, every user is logged out and nothing else is lost.

## Why

Redis is in the stack partly to be learned, which creates a standing temptation to give it more work — cached patient lists, denormalised timelines, "just this one counter that matters". Each of those individually looks reasonable and collectively turns a cache into an undocumented second database with no durability guarantees and no migration story.

Stating the boundary as one sentence makes the violation obvious in review, and gives a clear answer to "should this go in Redis?" that does not require re-deriving the argument every time.

## Consequences

Anything that must survive a restart goes in PostgreSQL. Rate-limit counters resetting on a Redis restart is acceptable; a consent record doing so is not, which is why consent lives in Postgres even though checking it on every request would be faster from a cache.
