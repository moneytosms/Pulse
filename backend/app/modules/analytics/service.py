"""Analytics business rules (P4.2, #53).

No SQL, no FastAPI imports (backend.md). This module owns no tables of
its own (ADR-0009 — no `summary_insight`, everything computed at request
time), so it has nothing to say beyond composing `records.service` (the
entry-based series) and `users.service` (Patient identity, for the flags
that read Patient fields directly rather than Medical Entries).

Threshold choices below (`_IMPLAUSIBLE_DOB_YEARS`, `_LONG_LIVED_DAYS`) are
not named anywhere in domain-model.md — the flags are "informational
only, they never block anything", so a documented, defensible default
stands in rather than blocking implementation on an unspecified number.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.transactions import transactional
from app.modules.analytics.schemas import DataQualityFlag
from app.modules.audit import service as audit_service
from app.modules.records import service as records_service
from app.modules.records.schemas import (
    LabTest,
    LabTrendPoint,
    MedicationSummary,
    MonthlyVisitCount,
    ProviderEntryCount,
)
from app.modules.users import service as users_service

# No date of birth on record before this is implausible rather than merely
# old — Synthea's oldest synthetic patients are not this old, and a real
# person past this age is vanishingly unlikely in this dataset.
_IMPLAUSIBLE_DOB_YEARS = 130

# A Provider-filed Patient nobody has claimed after this long is worth a
# human's attention; shorter and every walk-in filed yesterday would flag.
_LONG_LIVED_DAYS = 365


def _is_abnormal(
    value_numeric: float | None, *, reference_low: float | None, reference_high: float | None
) -> bool | None:
    """Compares a lab result against **its own row's** reference bounds
    only — never a hardcoded/global range (#54 acceptance criterion).
    `None` when there is nothing to compare (no numeric value, or no bounds
    recorded for this particular row)."""
    if value_numeric is None or (reference_low is None and reference_high is None):
        return None
    if reference_low is not None and value_numeric < reference_low:
        return True
    if reference_high is not None and value_numeric > reference_high:
        return True
    return False


@transactional
async def lab_trend(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    code_system: str,
    code: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTrendPoint]:
    _validate_window(from_date, to_date)
    await records_service.authorize_patient_access(session, actor, patient_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.ANALYTICS_VIEWED,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    points = await records_service.lab_trend(
        session,
        actor,
        patient_id,
        code_system=code_system,
        code=code,
        from_date=from_date,
        to_date=to_date,
    )
    return [
        p.model_copy(
            update={
                "is_abnormal": _is_abnormal(
                    p.value_numeric,
                    reference_low=p.reference_low,
                    reference_high=p.reference_high,
                )
            }
        )
        for p in points
    ]


@transactional
async def lab_tests(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTest]:
    _validate_window(from_date, to_date)
    await records_service.authorize_patient_access(session, actor, patient_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.ANALYTICS_VIEWED,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return await records_service.lab_tests(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


@transactional
async def visit_frequency_by_month(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MonthlyVisitCount]:
    _validate_window(from_date, to_date)
    await records_service.authorize_patient_access(session, actor, patient_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.ANALYTICS_VIEWED,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return await records_service.visit_frequency_by_month(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


@transactional
async def active_medications(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MedicationSummary]:
    _validate_window(from_date, to_date)
    await records_service.authorize_patient_access(session, actor, patient_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.ANALYTICS_VIEWED,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return await records_service.active_medications(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


@transactional
async def provider_entry_counts(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[ProviderEntryCount]:
    _validate_window(from_date, to_date)
    await records_service.authorize_patient_access(session, actor, patient_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.ANALYTICS_VIEWED,
        resource_type="patient",
        resource_id=patient_id,
        patient_id=patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return await records_service.provider_entry_counts(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


def _implausible_dob(dob: date) -> bool:
    today = datetime.now(UTC).date()
    return dob > today or dob < today.replace(year=today.year - _IMPLAUSIBLE_DOB_YEARS)


async def identity_data_quality_flags(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[DataQualityFlag]:
    """The four flags read straight from the Patient row — no Medical
    Entry involved, so `accessible_entries` never enters the picture.

    Identity fields are not clinical data (ADR-0007 bars the latter, not
    the former), but they are still personal data: a `patient_id` is a
    capability, and a signature without an actor is exactly how a stray
    id in a log turns into a disclosure. The gate follows the intended
    consumer rather than trusting the caller: Administrator (the
    data-quality queue — the only role with a legitimate batch reason to
    sweep identity gaps) or the Patient's own User (mirroring
    PATIENT_PROFILE_READ_SELF). Everyone else, including Clinicians —
    they see identity *through* consent-gated clinical access, not
    around it — gets `FORBIDDEN` (403: authenticated, role forbids it;
    no resource-existence leak, api-conventions.md).
    """
    patient = await users_service.get_patient(session, patient_id)
    # Same shape as the unauthorised case: absence here is a capability-
    # probe answer, not a data-quality result. (ADR-0007 is why this is
    # 403, not 404 — Administrators must learn nothing they cannot read.)
    if patient is None or not _may_read_identity(actor, patient.user_id):
        raise PulseError(
            ErrorCode.FORBIDDEN,
            "You do not have permission to read this patient's data-quality flags.",
            http_status=403,
        )

    flags: list[DataQualityFlag] = []
    if patient.date_of_birth is None:
        flags.append(DataQualityFlag.MISSING_DOB)
    elif _implausible_dob(patient.date_of_birth):
        flags.append(DataQualityFlag.IMPLAUSIBLE_DOB)
    if patient.phone is None:
        flags.append(DataQualityFlag.MISSING_CONTACT)
    if patient.user_id is None:
        age = datetime.now(UTC) - patient.created_at
        if age > timedelta(days=_LONG_LIVED_DAYS):
            flags.append(DataQualityFlag.UNCLAIMED_LONG_LIVED)
    return flags


def _may_read_identity(actor: Actor, owner_user_id: UUID | None) -> bool:
    return actor.role is Role.ADMINISTRATOR or (
        owner_user_id is not None and owner_user_id == actor.user_id
    )


async def data_quality_flags(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[DataQualityFlag]:
    flags = await identity_data_quality_flags(session, actor, patient_id)
    future_count = await records_service.future_dated_entry_count(session, actor, patient_id)
    if future_count > 0:
        flags.append(DataQualityFlag.FUTURE_DATED_ENTRY)
    return flags


def _validate_window(from_date: date | None, to_date: date | None) -> None:
    if from_date and to_date and from_date > to_date:
        raise PulseError(
            ErrorCode.VALIDATION_ERROR, "Date window must be ordered.", http_status=422
        )
