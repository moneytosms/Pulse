"""Audit repository — SQL for AuditEvent.

P3.8 (#45): `insert_event` (the only write) and `list_for_patient` (the
Patient's own filtered projection). `list_for_patient` joins to `"user"`
via raw SQL rather than importing `users.models` — same reason
`records/repository.py` reaches `access_permission`/`break_glass_access`
that way: the cross-module import lint forbids another module's
`models`/`repository`, not its tables. `provider_name`/`entry_type` come
out of `event_metadata` (set by the caller at emit time, never a join to
`records`' tables) so this module never needs to know about entries at
all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.audit.models import AuditAction, AuditEvent, AuditOutcome

_MAX_LIMIT = 100


async def count_non_patient_entry_views(
    session: AsyncSession, patient_id: UUID, since: datetime
) -> int:
    """Count of `ENTRY_VIEWED` events by a non-Patient actor against
    `patient_id`, strictly after `since`. Feeds "a clinician viewed your
    records" — the digest, never a per-view notification
    (domain-model.md, "Notifications")."""
    stmt = (
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.patient_id == patient_id,
            AuditEvent.action == AuditAction.ENTRY_VIEWED,
            AuditEvent.actor_role != Role.PATIENT,
            AuditEvent.occurred_at > since,
        )
    )
    return (await session.execute(stmt)).scalar_one()


async def insert_event(
    session: AsyncSession,
    *,
    actor_user_id: UUID | None,
    actor_role: Role,
    action: AuditAction,
    resource_type: str,
    resource_id: UUID | None,
    patient_id: UUID | None,
    outcome: AuditOutcome,
    request_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    event_metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """One `AuditEvent` row. Flushes only — the caller (`audit.service`)
    owns the commit (backend.md; matches `notifications/repository.py`)."""
    event = AuditEvent(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        patient_id=patient_id,
        outcome=outcome,
        request_id=request_id,
        ip=ip,
        user_agent=user_agent,
        event_metadata=event_metadata or {},
    )
    session.add(event)
    await session.flush()
    return event


@dataclass(frozen=True)
class PatientAuditRow:
    """One row of the Patient's own filtered projection. `actor_email` is
    the best available display name — `User` carries no separate display
    name (only Patients do), so a Clinician/Provider Staff actor's email
    is what the Patient sees; that's an intentional stand-in, not a leak
    of a raw identifier such as a user id."""

    id: UUID
    occurred_at: datetime
    actor_email: str | None
    actor_role: Role
    action: AuditAction
    provider_name: str | None
    entry_type: str | None


def _pack_cursor(occurred_at: datetime, event_id: UUID) -> str:
    return encode_cursor(f"{occurred_at.isoformat()}|{event_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = decode_cursor(cursor)
    ts, sep, uid = raw.partition("|")
    try:
        if not sep:
            raise ValueError("missing separator")
        return datetime.fromisoformat(ts), UUID(uid)
    except ValueError as exc:
        raise PulseError(ErrorCode.VALIDATION_ERROR, "Invalid cursor.") from exc


async def list_for_patient(
    session: AsyncSession,
    patient_id: UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[PatientAuditRow], str | None]:
    """`occurred_at DESC` keyset over `(occurred_at, id)` — never offset
    (api-conventions.md). Scoped to `patient_id` only: another patient's
    events are never in the result set to begin with, not filtered out
    after the fact."""
    limit = max(1, min(limit, _MAX_LIMIT))
    params: dict[str, Any] = {"patient_id": patient_id, "limit": limit + 1}
    cursor_clause = ""
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        cursor_clause = (
            "AND (ae.occurred_at < :c_at "
            "OR (ae.occurred_at = :c_at AND ae.id < :c_id)) "
        )
        params["c_at"] = c_at
        params["c_id"] = c_id
    stmt = text(
        "SELECT ae.id, ae.occurred_at, u.email AS actor_email, "
        "ae.actor_role, ae.action, "
        "ae.metadata ->> 'provider_name' AS provider_name, "
        "ae.metadata ->> 'entry_type' AS entry_type "
        "FROM audit_event ae "
        'LEFT JOIN "user" u ON u.id = ae.actor_user_id '
        "WHERE ae.patient_id = :patient_id " + cursor_clause + "ORDER BY ae.occurred_at DESC, "
        "ae.id DESC LIMIT :limit"
    )
    mapped = (await session.execute(stmt, params)).mappings().all()
    rows = [
        PatientAuditRow(
            id=row["id"],
            occurred_at=row["occurred_at"],
            actor_email=row["actor_email"],
            actor_role=Role(row["actor_role"]),
            action=AuditAction(row["action"]),
            provider_name=row["provider_name"],
            entry_type=row["entry_type"],
        )
        for row in mapped
    ]
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.occurred_at, tail.id)
    return rows, next_cursor
