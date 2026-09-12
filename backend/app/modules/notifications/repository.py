"""Notifications repository — all SQL for Notification / NotificationPreference.

Writes flush but do not commit — the calling service owns the transaction
boundary (same convention as `users/repository.py`, `records/repository.py`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.notifications.models import Notification, NotificationPreference
from app.modules.notifications.schemas import NotificationChannel, NotificationType

_MAX_LIMIT = 100


def _pack_cursor(created_at: datetime, notification_id: UUID) -> str:
    return encode_cursor(f"{created_at.isoformat()}|{notification_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = decode_cursor(cursor)
    ts, sep, uid = raw.partition("|")
    try:
        if not sep:
            raise ValueError("missing separator")
        return datetime.fromisoformat(ts), UUID(uid)
    except ValueError as exc:
        raise PulseError(ErrorCode.VALIDATION_ERROR, "Invalid cursor.") from exc


async def insert_notification(
    session: AsyncSession,
    user_id: UUID,
    type_: NotificationType,
    params: dict[str, Any],
) -> Notification:
    row = Notification(user_id=user_id, type=type_, params=params)
    session.add(row)
    await session.flush()
    return row


async def list_notifications(
    session: AsyncSession,
    user_id: UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[Notification], str | None]:
    """`created_at DESC`. Opaque keyset cursor over `(created_at, id)` —
    never offset (api-conventions.md)."""
    limit = max(1, min(limit, _MAX_LIMIT))
    stmt = select(Notification).where(Notification.user_id == user_id)
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        stmt = stmt.where(
            or_(
                Notification.created_at < c_at,
                (Notification.created_at == c_at) & (Notification.id < c_id),
            )
        )
    stmt = stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.created_at, tail.id)
    return rows, next_cursor


async def get_notification(
    session: AsyncSession, user_id: UUID, notification_id: UUID
) -> Notification | None:
    stmt = select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_read(
    session: AsyncSession, user_id: UUID, notification_id: UUID, read_at: datetime
) -> Notification | None:
    """Sets `read_at` if unset. Returns None when no row matched — either
    it does not exist, belongs to another user, or is already read; the
    caller distinguishes those with `get_notification`."""
    result = await session.execute(
        update(Notification)
        .where(
            (Notification.id == notification_id)
            & (Notification.user_id == user_id)
            & Notification.read_at.is_(None)
        )
        .values(read_at=read_at)
    )
    if not isinstance(result, CursorResult) or result.rowcount == 0:
        return None
    return await get_notification(session, user_id, notification_id)


async def get_last_digest_created_at(session: AsyncSession, user_id: UUID) -> datetime | None:
    stmt = (
        select(Notification.created_at)
        .where(
            Notification.user_id == user_id,
            Notification.type == NotificationType.DAILY_DIGEST,
        )
        .order_by(Notification.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_preferences(session: AsyncSession, user_id: UUID) -> list[NotificationPreference]:
    stmt = select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    return list((await session.execute(stmt)).scalars().all())


async def get_preference(
    session: AsyncSession,
    user_id: UUID,
    notification_type: NotificationType,
    channel: NotificationChannel,
) -> NotificationPreference | None:
    stmt = select(NotificationPreference).where(
        NotificationPreference.user_id == user_id,
        NotificationPreference.notification_type == notification_type,
        NotificationPreference.channel == channel,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_preference(
    session: AsyncSession,
    user_id: UUID,
    notification_type: NotificationType,
    channel: NotificationChannel,
    enabled: bool,
) -> NotificationPreference:
    existing = await get_preference(session, user_id, notification_type, channel)
    if existing is not None:
        existing.enabled = enabled
        await session.flush()
        return existing
    row = NotificationPreference(
        user_id=user_id,
        notification_type=notification_type,
        channel=channel,
        enabled=enabled,
    )
    session.add(row)
    await session.flush()
    return row
