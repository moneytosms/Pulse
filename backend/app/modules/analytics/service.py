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
from app.modules.analytics.schemas import DataQualityFlag
from app.modules.records import service as records_service
from app.modules.records.schemas import (
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


async def lab_trend(
    session: AsyncSession, actor: Actor, patient_id: UUID, *, code_system: str, code: str
) -> list[LabTrendPoint]:
    return await records_service.lab_trend(
        session, actor, patient_id, code_system=code_system, code=code
    )


async def visit_frequency_by_month(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[MonthlyVisitCount]:
    return await records_service.visit_frequency_by_month(session, actor, patient_id)


async def active_medications(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[MedicationSummary]:
    return await records_service.active_medications(session, actor, patient_id)


async def provider_entry_counts(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[ProviderEntryCount]:
    return await records_service.provider_entry_counts(session, actor, patient_id)


def _implausible_dob(dob: date) -> bool:
    today = datetime.now(UTC).date()
    return dob > today or dob < today.replace(year=today.year - _IMPLAUSIBLE_DOB_YEARS)


async def identity_data_quality_flags(
    session: AsyncSession, patient_id: UUID
) -> list[DataQualityFlag]:
    """The four flags read straight from the Patient row — no Medical
    Entry involved, so no `actor` needed (nothing here is clinical
    content; an Administrator working the data-quality queue is exactly
    who this is for, and ADR-0007 only bars clinical data, not identity
    fields already visible in the duplicate-review queue)."""
    patient = await users_service.get_patient(session, patient_id)
    if patient is None:
        return []

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


async def data_quality_flags(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[DataQualityFlag]:
    flags = await identity_data_quality_flags(session, patient_id)
    future_count = await records_service.future_dated_entry_count(session, actor, patient_id)
    if future_count > 0:
        flags.append(DataQualityFlag.FUTURE_DATED_ENTRY)
    return flags
