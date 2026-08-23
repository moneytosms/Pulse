# Plan 001: Make `decode_cursor` raise a structured `PulseError` on malformed input

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 91f0c56..HEAD -- backend/app/core/pagination.py`
> If this file changed since this plan was written, compare the "Current
> state" excerpt below against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `91f0c56`, 2026-08-23

## Why this matters

`decode_cursor` in `backend/app/core/pagination.py` is the opaque-cursor codec every future list endpoint (`?cursor=&limit=`) will call to decode a client-supplied `cursor` query param — untrusted input by definition. Right now a malformed cursor raises a raw `binascii.Error` or `UnicodeDecodeError` straight out of the function. Nothing in `backend/app/core/exceptions.py` catches those, so a bad cursor from a client currently becomes an unhandled 500 with a stack-trace-shaped body instead of the project's coded error envelope (`.claude/rules/backend.md`: "Error responses are always the coded envelope"). No route calls this yet — Phase 0 has no wired endpoints — so this is a small, safe, currently-inert fix: get it right once now, no route touches it under time pressure later.

## Current state

- `backend/app/core/pagination.py` — full file, current contents:

```python
"""Cursor pagination: opaque cursor codec plus the generic Page[T] envelope."""

import base64
from typing import Generic, TypeVar

from app.core.schema import PulseSchema

T = TypeVar("T")


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    return base64.urlsafe_b64decode(cursor.encode()).decode()


class Page(PulseSchema, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
```

- `backend/app/core/errors.py` defines `ErrorCode` (currently: `NOT_FOUND`, `VALIDATION_ERROR`, `UNAUTHORIZED`, `FORBIDDEN`, `CONFLICT`, `INTERNAL_ERROR`) and `ErrorDetail`/`ErrorBody`/`ErrorEnvelope`.
- `backend/app/core/exceptions.py` defines `PulseError(code, message, *, http_status=400, details=None)` — the exception every service/route-boundary error should raise; `pulse_error_handler` renders it as the envelope. Exemplar of the pattern to match:

```python
class PulseError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        http_status: int = status.HTTP_400_BAD_REQUEST,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details or []
```

- Repo convention (`.claude/rules/backend.md`): error codes are `SCREAMING_SNAKE_CASE`, live in the one `ErrorCode` enum, stable forever. `VALIDATION_ERROR` already exists and fits a malformed cursor — do not add a new code for this.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Syntax check | `python3 -m py_compile backend/app/core/pagination.py` | exit 0 |
| Import check (if deps installed) | `cd backend && uv run python -c "from app.core.pagination import decode_cursor"` | exit 0, or note "uv/deps not installed" and rely on py_compile only |

No test runner or lint config exists yet in this repo (Phase 0, pre-`pyproject.toml`) — do not invent one. Use the commands above only.

## Scope

**In scope** (the only file you should modify):
- `backend/app/core/pagination.py`

**Out of scope** (do NOT touch, even though they look related):
- `backend/app/core/errors.py`, `backend/app/core/exceptions.py` — read-only reference, `VALIDATION_ERROR` already exists, no new error code needed.
- Any module's `routes.py` — no endpoint calls `decode_cursor` yet in Phase 0; do not add one as part of this plan.
- `encode_cursor` — it only ever encodes trusted server-generated values; leave it as-is.

## Steps

### Step 1: Wrap `decode_cursor`'s body to raise `PulseError` on malformed input

Replace the current `decode_cursor` with a version that catches decode failures and re-raises as `PulseError(ErrorCode.VALIDATION_ERROR, ...)`. Import `PulseError` from `app.core.exceptions` and `ErrorCode` from `app.core.errors` at the top of the file. Catch `(binascii.Error, UnicodeDecodeError, ValueError)` — `base64.urlsafe_b64decode` can raise `binascii.Error` for bad padding/characters, and `.decode()` can raise `UnicodeDecodeError` if the decoded bytes aren't valid UTF-8.

Target shape:

```python
"""Cursor pagination: opaque cursor codec plus the generic Page[T] envelope."""

import base64
import binascii
from typing import Generic, TypeVar

from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.schema import PulseSchema

T = TypeVar("T")


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise PulseError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid cursor.",
        ) from exc


class Page(PulseSchema, Generic[T]):
    items: list[T]
    next_cursor: str | None = None
```

**Verify**: `python3 -m py_compile backend/app/core/pagination.py` → exit 0.

### Step 2: Confirm there's no import cycle

`app.core.exceptions` imports from `app.core.errors` and `app.core.middleware`, not from `app.core.pagination` — so `pagination.py` importing from `exceptions.py` is a one-directional edge and safe. Confirm by reading `backend/app/core/exceptions.py`'s import block and checking it does not import `app.core.pagination`.

**Verify**: `grep -n "^from app.core" backend/app/core/exceptions.py` → shows imports from `app.core.errors` and `app.core.middleware` only, no `app.core.pagination`.

## Test plan

No test runner exists yet in this repo (Phase 0). Do not add a `pytest`-based test file — there is no `pyproject.toml`/`uv.lock` for it to run against yet, and adding one prematurely is out of scope for this plan. Once the backend gets a real test harness (a later Phase 0/1 step, not this plan), add a unit test asserting: (a) `decode_cursor(encode_cursor("x"))` round-trips, (b) `decode_cursor("not-valid-base64!!!")` raises `PulseError` with `code == ErrorCode.VALIDATION_ERROR`. Leave this as a follow-up, not a step here.

## Done criteria

Machine-checkable. ALL must hold:

- [ ] `python3 -m py_compile backend/app/core/pagination.py` exits 0
- [ ] `grep -n "PulseError" backend/app/core/pagination.py` shows the import and one raise site
- [ ] `git status --short` shows only `backend/app/core/pagination.py` modified
- [ ] `plans/README.md` status row for 001 updated

## STOP conditions

Stop and report back (do not improvise) if:

- `backend/app/core/pagination.py`'s current contents don't match the "Current state" excerpt above (file has drifted).
- `backend/app/core/exceptions.py` no longer defines `PulseError` with the `(code, message, *, http_status, details)` signature shown above.
- `ErrorCode.VALIDATION_ERROR` no longer exists in `backend/app/core/errors.py`.

## Maintenance notes

- The first route that actually accepts a `cursor` query param (Phase 1+) should have a negative test asserting a malformed cursor returns the coded envelope with `VALIDATION_ERROR`, not a 500 — per `.claude/rules/backend.md`'s "write the negative test first."
- If a global exception-handler test suite is added later, this is a natural case to include: `PulseError` raised from a helper (not a route body) should still be caught by `pulse_error_handler` since FastAPI's exception handler dispatch works on the exception type regardless of where it's raised.
