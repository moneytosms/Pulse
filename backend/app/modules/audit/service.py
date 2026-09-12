"""Audit business rules. No SQL, no FastAPI imports (backend.md).

`emit()` (P3.8, #45) is the one way an `AuditEvent` gets written — called
explicitly from a module's service layer at the point of access, never
an ORM hook: the most important events are *reads*, and a read produces
no write for a hook to fire on (clinical-safety.md). `AuditMetadata` is
the whole enforcement of "no clinical value in `event_metadata`, ever" —
it is a closed, typed set of non-clinical fields (identifiers, counts,
entry types — `audit/models.py`), so there is no field a diagnosis or lab
value could be passed through by accident. `emit()` takes an
`AuditMetadata`, never a free-form `dict`.

`list_for_patient()` is the Patient's own filtered projection
(`AUDIT_READ_SELF`) — always scoped to the caller's own Patient, 404 (not
403) on any mismatch, matching every other clinical read
(clinical-safety.md).

`count_non_patient_entry_views` is the one query the notification
module's daily digest composes from (P3.9, #43) — imported as
`app.modules.audit.service`, never `.repository` (cross-module import
lint, backend.md).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import Page
from app.modules.audit import repository

# Re-exported (explicitly, for mypy) so a caller wiring `emit()` can import
# both the action/outcome enums and this module in one line — see
# `records/service.py`, which imports `AuditAction`/`AuditOutcome` from
# here rather than `app.modules.audit.models` (cross-module import lint:
# another module's `models`/`repository` is forbidden, `service` is not).
from app.modules.audit.models import AuditAction as AuditAction
from app.modules.audit.models import AuditOutcome as AuditOutcome
from app.modules.audit.schemas import AuditEventProjection
from app.modules.users import service as users_service


async def count_non_patient_entry_views(
    session: AsyncSession, patient_id: UUID, since: datetime
) -> int:
    return await repository.count_non_patient_entry_views(session, patient_id, since)


@dataclass(frozen=True)
class AuditMetadata:
    """The only fields `emit()` can carry into `audit_event.metadata`.
    Identifiers, counts, entry types — never a clinical value
    (clinical-safety.md, `audit/models.py`). Add a field here only for
    something that is provably non-clinical; do not widen this into a
    free-form dict."""

    entry_type: str | None = None
    provider_name: str | None = None
    count: int | None = None
    justification: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _not_found() -> PulseError:
    return PulseError(ErrorCode.NOT_FOUND, "No such audit trail.", http_status=404)


async def emit(
    session: AsyncSession,
    *,
    actor: Actor,
    action: AuditAction,
    resource_type: str,
    resource_id: UUID | None,
    patient_id: UUID | None,
    outcome: AuditOutcome,
    metadata: AuditMetadata | None = None,
    request_id: str | None = None,
) -> None:
    """Write one `AuditEvent` and commit. `actor_role` is denormalised
    from `actor.role` at write time (roles change; history must not).
    Commits inline — matching `notifications/service.py`'s inline commits
    after each repository write — so a caller mid-request never has to
    remember to flush the audit trail itself."""
    await repository.insert_event(
        session,
        actor_user_id=actor.user_id,
        actor_role=actor.role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        patient_id=patient_id,
        outcome=outcome,
        request_id=request_id,
        event_metadata=metadata.to_dict() if metadata is not None else {},
    )
    await session.commit()


def _to_projection(row: repository.PatientAuditRow) -> AuditEventProjection:
    return AuditEventProjection(
        id=row.id,
        occurred_at=row.occurred_at,
        actor_name=row.actor_email or "Unknown",
        actor_role=row.actor_role.value,
        provider_name=row.provider_name,
        action=row.action.value,
        entry_type=row.entry_type,
    )


async def list_for_patient(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID | None,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[AuditEventProjection]:
    """The signed-in Patient's own filtered projection. `patient_id` is
    accepted (matching the route's `?patientId=`) only to be checked
    against the actor's own Patient — never as a way to read someone
    else's trail. A mismatch, or an actor who owns no Patient, is 404,
    never 403 (clinical-safety.md)."""
    own = await users_service.get_own_patient_profile(session, actor)
    if own is None or (patient_id is not None and patient_id != own.id):
        raise _not_found()
    rows, next_cursor = await repository.list_for_patient(
        session, own.id, cursor=cursor, limit=limit
    )
    return Page[AuditEventProjection](
        items=[_to_projection(r) for r in rows], next_cursor=next_cursor
    )
