"""Consent (P3.6, #42) + break-glass (P3.7, #44) business rules.

No SQL, no FastAPI imports (backend.md). Grant is step-up gated at the
route; revoke is not — withdrawing access is the frictionless direction
(clinical-safety.md). Revoking deletes the derived `access_permission`
row in the same transaction as the `Consent.revoked_at` stamp — that
delete *is* the "no cached permission" mechanism, not a TTL, so a session
reading concurrently loses access on its very next query.

Notification judgement calls (flagged in the PR/report, not guessed
silently):
  - Grant notifies nobody. `CONSENT_GRANTED` is the Patient's own action;
    notifying the Patient of their own action is not useful, and the
    grantee has no route to read an in-app notification at all
    (`NOTIFICATION_READ_SELF` is Patient-only) unless the type is
    mandatory (which this is not). The audit event is the record of it.
  - Revoke notifies the grantee (not the Patient — the Patient is the one
    revoking). `CONSENT_REVOKED` is mandatory (`MANDATORY_TYPES`), so
    `notify()` also fires an immediate email to the grantee regardless of
    the in-app read gate — the person who just lost access is the one who
    needs to hear about it, immediately.

Break-glass's "CRITICAL audit event" (clinical-safety.md) is represented
as `AuditAction.BREAK_GLASS_ACCESS` itself, not a separate severity field:
`audit_event` has no severity column, and this module does not add one —
the action enum already names exactly one thing, access without consent,
and that is what makes it loud. Adding a schema-wide severity concept for
one action would be new database surface for a single-caller distinction
the enum already carries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.notifications import NotificationProvider
from app.core.actor import Actor
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import Page
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditAction, AuditMetadata, AuditOutcome
from app.modules.consent import repository
from app.modules.consent.models import BreakGlassAccess
from app.modules.consent.models import Consent as ConsentRow
from app.modules.consent.schemas import (
    BreakGlassGrant,
    Consent,
    ConsentCreate,
    ConsentStatus,
    RevocationRequest,
)
from app.modules.notifications import service as notifications_service
from app.modules.notifications.schemas import NotificationType
from app.modules.users import service as users_service

_MIN_EXPIRY = timedelta(days=1)
_MAX_EXPIRY = timedelta(days=365)
_BREAK_GLASS_WINDOW = timedelta(minutes=60)


class TaskScheduler(Protocol):
    """Structural match for `fastapi.BackgroundTasks`, same shape as
    `notifications.service.TaskScheduler` — kept local so this module does
    not import another module's non-`service` internals."""

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None: ...


def _not_found() -> PulseError:
    return PulseError(ErrorCode.NOT_FOUND, "No such consent.", http_status=404)


def _status(row: ConsentRow, now: datetime) -> ConsentStatus:
    if row.revoked_at is not None:
        return ConsentStatus.REVOKED
    if row.expires_at <= now:
        return ConsentStatus.EXPIRED
    return ConsentStatus.ACTIVE


def _to_wire(row: ConsentRow) -> Consent:
    return Consent(
        id=row.id,
        patient_id=row.patient_id,
        grantee_user_id=row.grantee_user_id,
        entry_types=row.entry_types,
        from_date=row.from_date,
        to_date=row.to_date,
        purpose=row.purpose,
        purpose_text=row.purpose_text,
        status=_status(row, datetime.now(UTC)),
        expires_at=row.expires_at,
        granted_at=row.granted_at,
        revoked_at=row.revoked_at,
        revocation_reason=row.revocation_reason,
    )


def _break_glass_to_wire(row: BreakGlassAccess) -> BreakGlassGrant:
    return BreakGlassGrant(
        id=row.id,
        patient_id=row.patient_id,
        clinician_user_id=row.clinician_user_id,
        justification=row.justification,
        granted_at=row.granted_at,
        expires_at=row.expires_at,
    )


async def grant_consent(session: AsyncSession, actor: Actor, payload: ConsentCreate) -> Consent:
    """Step-up gated at the route. `expires_at` must be 1-365 days out;
    Consent + its derived AccessPermission are written in one transaction
    (`repository.create_consent_and_permission`)."""
    own = await users_service.get_own_patient_profile(session, actor)
    if own is None:
        raise _not_found()
    now = datetime.now(UTC)
    if not (now + _MIN_EXPIRY <= payload.expires_at <= now + _MAX_EXPIRY):
        raise PulseError(
            ErrorCode.CONSENT_EXPIRY_OUT_OF_RANGE,
            "Consent expiry must be between 1 and 365 days from now.",
            http_status=422,
        )
    row = await repository.create_consent_and_permission(
        session,
        patient_id=own.id,
        grantee_user_id=payload.grantee_user_id,
        entry_types=payload.entry_types,
        from_date=payload.from_date,
        to_date=payload.to_date,
        purpose=payload.purpose,
        purpose_text=payload.purpose_text,
        expires_at=payload.expires_at,
    )
    await session.commit()
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.CONSENT_GRANTED,
        resource_type="consent",
        resource_id=row.id,
        patient_id=own.id,
        outcome=AuditOutcome.SUCCESS,
    )
    return _to_wire(row)


async def revoke_consent(
    session: AsyncSession,
    actor: Actor,
    consent_id: UUID,
    payload: RevocationRequest,
    *,
    provider: NotificationProvider | None = None,
    background_tasks: TaskScheduler | None = None,
) -> Consent:
    """No step-up (clinical-safety.md: withdrawing access is frictionless).
    Deletes the derived `access_permission` row in the same transaction as
    the `revoked_at` stamp — a session reading concurrently loses access on
    its very next query, not on some later cache expiry."""
    own = await users_service.get_own_patient_profile(session, actor)
    if own is None:
        raise _not_found()
    existing = await repository.get_consent_by_id(session, consent_id)
    if existing is None or existing.patient_id != own.id:
        raise _not_found()
    row = await repository.revoke_consent(
        session, consent_id, reason=payload.reason, revoked_at=datetime.now(UTC)
    )
    if row is None:
        raise _not_found()
    await session.commit()
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.CONSENT_REVOKED,
        resource_type="consent",
        resource_id=row.id,
        patient_id=own.id,
        outcome=AuditOutcome.SUCCESS,
    )
    # Mandatory type: notify() emails the grantee immediately regardless of
    # any in-app preference — see the module docstring for why the grantee,
    # not the Patient, is the target here.
    await notifications_service.notify(
        session,
        row.grantee_user_id,
        NotificationType.CONSENT_REVOKED,
        {"patientId": str(own.id)},
        provider=provider,
        background_tasks=background_tasks,
    )
    return _to_wire(row)


async def list_consents(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID | None,
    *,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[Consent]:
    """The signed-in Patient's own consents. `patient_id` (from
    `?patientId=`) is accepted only to be checked against the actor's own
    Patient, matching `audit.service.list_for_patient` — never a way to
    read someone else's. Mismatch or no owned Patient is 404, never 403."""
    own = await users_service.get_own_patient_profile(session, actor)
    if own is None or (patient_id is not None and patient_id != own.id):
        raise _not_found()
    rows, next_cursor = await repository.list_consents_for_patient(
        session, own.id, cursor=cursor, limit=limit
    )
    return Page[Consent](items=[_to_wire(r) for r in rows], next_cursor=next_cursor)


async def request_break_glass(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    justification: str,
    *,
    provider: NotificationProvider | None = None,
    background_tasks: TaskScheduler | None = None,
) -> BreakGlassGrant:
    """Emergency access without Consent (#44). Exactly 60 minutes, not
    configurable. The audit event is written synchronously, before this
    returns; the Patient (when registered — `patient.user_id` is nullable
    and load-bearing, clinical-safety.md) is notified immediately via the
    mandatory `BREAK_GLASS_ACCESS` type, never the digest."""
    patient = await users_service.get_patient(session, patient_id)
    if patient is None:
        raise _not_found()
    expires_at = datetime.now(UTC) + _BREAK_GLASS_WINDOW
    grant = await repository.create_break_glass(
        session,
        patient_id=patient_id,
        clinician_user_id=actor.user_id,
        justification=justification,
        expires_at=expires_at,
    )
    await session.commit()
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.BREAK_GLASS_ACCESS,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=AuditOutcome.SUCCESS,
        metadata=AuditMetadata(justification=justification),
    )
    if patient.user_id is not None:
        await notifications_service.notify(
            session,
            patient.user_id,
            NotificationType.BREAK_GLASS_ACCESS,
            {},
            provider=provider,
            background_tasks=background_tasks,
        )
    return _break_glass_to_wire(grant)
