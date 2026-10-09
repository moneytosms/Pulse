"""Audit SQL, using owned models and the users module's live identity scope.

Historical rows remain unchanged; current tombstones let the surviving owner
read the original identity's audit history. Actor emails are resolved through
the users service after querying, never by joining foreign tables here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Role
from app.core.pagination import encode_cursor, unpack_cursor
from app.modules.audit.models import AuditAction, AuditEvent, AuditOutcome
from app.modules.users import service as users_service

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
    actor_role: Role | None,
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
        occurred_at=func.clock_timestamp(),
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
    actor_user_id: UUID | None
    actor_email: str | None
    actor_role: Role | None
    action: AuditAction
    provider_name: str | None
    entry_type: str | None


def _pack_cursor(occurred_at: datetime, event_id: UUID) -> str:
    return encode_cursor(f"{occurred_at.isoformat()}|{event_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    return unpack_cursor(cursor)


async def list_for_patient(
    session: AsyncSession,
    patient_id: UUID,
    *,
    cursor: str | None = None,
    limit: int = 50,
    action: AuditAction | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    actor_role: Role | None = None,
) -> tuple[list[PatientAuditRow], str | None]:
    """`occurred_at DESC` keyset over `(occurred_at, id)` — never offset
    (api-conventions.md). Scoped to `patient_id` only: another patient's
    events are never in the result set to begin with, not filtered out
    after the fact."""
    limit = max(1, min(limit, _MAX_LIMIT))
    stmt = select(AuditEvent).where(
        users_service.audit_patient_scope(patient_id, AuditEvent.patient_id.__clause_element__())
    )
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if since is not None:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until is not None:
        stmt = stmt.where(AuditEvent.occurred_at < until)
    if actor_role is not None:
        stmt = stmt.where(AuditEvent.actor_role == actor_role)
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        stmt = stmt.where(
            or_(
                AuditEvent.occurred_at < c_at,
                (AuditEvent.occurred_at == c_at) & (AuditEvent.id < c_id),
            )
        )
    events = (
        await session.scalars(
            stmt.order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit + 1)
        )
    ).all()
    rows = [
        PatientAuditRow(
            id=event.id,
            occurred_at=event.occurred_at,
            actor_user_id=event.actor_user_id,
            actor_email=None,
            actor_role=event.actor_role,
            action=event.action,
            provider_name=event.event_metadata.get("provider_name"),
            entry_type=event.event_metadata.get("entry_type"),
        )
        for event in events
    ]
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.occurred_at, tail.id)
    return rows, next_cursor
