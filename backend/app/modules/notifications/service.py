"""Notification business rules (P3.9, #43).

No SQL, no FastAPI imports (backend.md). The one FastAPI-shaped exception
is `TaskScheduler` below: a structural `Protocol` matching
`fastapi.BackgroundTasks.add_task`, so a route can hand this module a real
`BackgroundTasks` without the module importing FastAPI.

`MANDATORY_TYPES` is the one allowlist for "never subject to a preference
check, never shown in the preferences list — absent, not locked" (issue
#43). Consent-granted, record-uploaded and the daily digest are all
opt-outable; a break-glass access and a consent revocation are not — a
Patient must always hear about those.

"A clinician viewed your records" is a **read-computed daily digest**, not
a per-view notification (domain-model.md, "Notifications"; same
computed-on-read reasoning as ADR-0009 — no scheduler exists anywhere in
this stack). `list_notifications` computes it inline, from `audit_event`
via `app.modules.audit.service`, before paginating: a new digest row is
written only when there is at least one non-Patient view since the last
digest, so a read that finds nothing new writes nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.notifications import NotificationProvider
from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import Page
from app.modules.audit import service as audit_service
from app.modules.notifications import repository
from app.modules.notifications.models import Notification as NotificationRow
from app.modules.notifications.schemas import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationType,
)
from app.modules.users import service as users_service

# Never subject to a preference check; never listed as a preference the
# Patient can toggle (absent, not shown locked — issue #43).
MANDATORY_TYPES: frozenset[NotificationType] = frozenset(
    {NotificationType.BREAK_GLASS_ACCESS, NotificationType.CONSENT_REVOKED}
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_TITLES: dict[NotificationType, str] = {
    NotificationType.CONSENT_GRANTED: "New consent granted",
    NotificationType.CONSENT_REVOKED: "Consent revoked",
    NotificationType.RECORD_UPLOADED: "New record uploaded",
    NotificationType.BREAK_GLASS_ACCESS: "Emergency access to your records",
    NotificationType.DAILY_DIGEST: "Your records were viewed",
}


class TaskScheduler(Protocol):
    """Structural match for `fastapi.BackgroundTasks` — a Protocol, not an
    import, so this module stays FastAPI-free."""

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None: ...


def _render(type_: NotificationType, params: dict[str, Any]) -> tuple[str, str]:
    """English-default title/body from `type` + `params`. A placeholder
    pending the locale-catalog rendering the frontend owns (frontend.md);
    never clinical content — only counts and identifiers
    (clinical-safety.md)."""
    title = _TITLES[type_]
    if type_ is NotificationType.DAILY_DIGEST:
        count = params.get("viewCount", 0)
        return title, f"Your records were viewed {count} time(s) since you last checked."
    return title, title


def _to_wire(row: NotificationRow) -> Notification:
    title, body = _render(row.type, row.params)
    return Notification(
        id=row.id,
        type=row.type,
        title=title,
        body=body,
        read_at=row.read_at,
        created_at=row.created_at,
    )


def _not_found() -> PulseError:
    return PulseError(ErrorCode.NOT_FOUND, "No such notification.", http_status=404)


async def _channel_enabled(
    session: AsyncSession,
    user_id: UUID,
    type_: NotificationType,
    channel: NotificationChannel,
) -> bool:
    pref = await repository.get_preference(session, user_id, type_, channel)
    return True if pref is None else pref.enabled


async def notify(
    session: AsyncSession,
    user_id: UUID,
    type_: NotificationType,
    params: dict[str, Any],
    *,
    provider: NotificationProvider | None = None,
    background_tasks: TaskScheduler | None = None,
) -> Notification | None:
    """Insert one Notification. A non-mandatory type is gated on the
    IN_APP preference (default enabled, so an unset preference behaves as
    "on"); a mandatory type always fires and is never asked. Immediate
    delivery — Mailpit through `provider`, scheduled via
    `background_tasks` so the caller's request is never slowed by SMTP —
    only happens for mandatory types; the digest and every opt-outable
    type are in-app only."""
    mandatory = type_ in MANDATORY_TYPES
    if not mandatory and not await _channel_enabled(
        session, user_id, type_, NotificationChannel.IN_APP
    ):
        return None
    row = await repository.insert_notification(session, user_id, type_, params)
    await session.commit()
    if mandatory and provider is not None and background_tasks is not None:
        user = await users_service.get_user(session, user_id)
        if user is not None:
            background_tasks.add_task(
                provider.send,
                NotificationChannel.EMAIL.value,
                user.email,
                type_.value,
                params,
            )
    return _to_wire(row)


async def _maybe_create_daily_digest(session: AsyncSession, actor: Actor) -> None:
    if actor.role is not Role.PATIENT:
        return
    profile = await users_service.get_own_patient_profile(session, actor)
    if profile is None:
        return
    since = await repository.get_last_digest_created_at(session, actor.user_id) or _EPOCH
    view_count = await audit_service.count_non_patient_entry_views(session, profile.id, since)
    if view_count == 0:
        return
    await notify(session, actor.user_id, NotificationType.DAILY_DIGEST, {"viewCount": view_count})


async def list_notifications(
    session: AsyncSession, actor: Actor, *, cursor: str | None = None, limit: int = 50
) -> Page[Notification]:
    await _maybe_create_daily_digest(session, actor)
    rows, next_cursor = await repository.list_notifications(
        session, actor.user_id, cursor=cursor, limit=limit
    )
    return Page[Notification](items=[_to_wire(r) for r in rows], next_cursor=next_cursor)


async def mark_read(session: AsyncSession, actor: Actor, notification_id: UUID) -> Notification:
    updated = await repository.mark_read(
        session, actor.user_id, notification_id, datetime.now(UTC)
    )
    if updated is not None:
        await session.commit()
        return _to_wire(updated)
    # rowcount 0: either it does not exist / belongs to someone else, or it
    # was already read — idempotent, so the latter returns the current row.
    existing = await repository.get_notification(session, actor.user_id, notification_id)
    if existing is None:
        raise _not_found()
    return _to_wire(existing)


async def list_preferences(session: AsyncSession, actor: Actor) -> list[NotificationPreference]:
    """Every non-mandatory (type, channel) pair, defaulting to enabled. A
    mandatory type never appears — absent, not shown locked (issue #43)."""
    stored = {
        (row.notification_type, row.channel): row.enabled
        for row in await repository.get_preferences(session, actor.user_id)
    }
    return [
        NotificationPreference(notification_type=t, channel=c, enabled=stored.get((t, c), True))
        for t in NotificationType
        if t not in MANDATORY_TYPES
        for c in NotificationChannel
    ]


async def set_preference(
    session: AsyncSession, actor: Actor, payload: NotificationPreference
) -> NotificationPreference:
    if payload.notification_type in MANDATORY_TYPES:
        raise PulseError(
            ErrorCode.NOTIFICATION_TYPE_MANDATORY,
            "This notification type cannot be disabled.",
            http_status=422,
        )
    await repository.upsert_preference(
        session,
        actor.user_id,
        payload.notification_type,
        payload.channel,
        payload.enabled,
    )
    await session.commit()
    return payload
