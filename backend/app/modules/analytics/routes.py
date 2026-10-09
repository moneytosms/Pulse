"""Analytics HTTP surface (P4.2/#53 composition, P4.3/#54 abnormality flag).

HTTP only — parse, guard, delegate (backend.md). No `summary_insight`
table (ADR-0009): every value here is computed at request time.

`data-quality-flags` is reachable by a Patient reading their own flags or
an Administrator sweeping the queue — both hold
`ANALYTICS_DATA_QUALITY_READ`, and `service.data_quality_flags` narrows
further to exactly those two cases, denying anyone else with FORBIDDEN.
Every other route here reads clinical data, so it is `RECORDS_READ` —
the same permission `records.routes` uses, which no Administrator holds
(ADR-0007).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.db.session import get_session
from app.modules.analytics import service
from app.modules.analytics.schemas import DataQualityFlag
from app.modules.auth.dependencies import AuthContext, current_user, requires
from app.modules.records.schemas import (
    LabTest,
    LabTrendPoint,
    MedicationSummary,
    MonthlyVisitCount,
    ProviderEntryCount,
)

router = APIRouter(prefix="/api/v1/patients/{patient_id}/analytics", tags=["analytics"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]


@router.get("/lab-tests", dependencies=[requires(Permission.RECORDS_READ)])
async def get_lab_tests(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> list[LabTest]:
    return await service.lab_tests(
        session, ctx.actor, patient_id, from_date=from_date, to_date=to_date
    )


@router.get("/lab-trend", dependencies=[requires(Permission.RECORDS_READ)])
async def get_lab_trend(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    code_system: Annotated[str, Query(alias="codeSystem")],
    code: str,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> list[LabTrendPoint]:
    return await service.lab_trend(
        session,
        ctx.actor,
        patient_id,
        code_system=code_system,
        code=code,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/visit-frequency", dependencies=[requires(Permission.RECORDS_READ)])
async def get_visit_frequency(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> list[MonthlyVisitCount]:
    return await service.visit_frequency_by_month(
        session, ctx.actor, patient_id, from_date=from_date, to_date=to_date
    )


@router.get("/active-medications", dependencies=[requires(Permission.RECORDS_READ)])
async def get_active_medications(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> list[MedicationSummary]:
    return await service.active_medications(
        session, ctx.actor, patient_id, from_date=from_date, to_date=to_date
    )


@router.get("/provider-entry-counts", dependencies=[requires(Permission.RECORDS_READ)])
async def get_provider_entry_counts(
    patient_id: UUID,
    ctx: CurrentUser,
    session: SessionDep,
    from_date: Annotated[date | None, Query(alias="fromDate")] = None,
    to_date: Annotated[date | None, Query(alias="toDate")] = None,
) -> list[ProviderEntryCount]:
    return await service.provider_entry_counts(
        session, ctx.actor, patient_id, from_date=from_date, to_date=to_date
    )


@router.get(
    "/data-quality-flags",
    dependencies=[requires(Permission.ANALYTICS_DATA_QUALITY_READ)],
)
async def get_data_quality_flags(
    patient_id: UUID, ctx: CurrentUser, session: SessionDep
) -> list[DataQualityFlag]:
    return await service.data_quality_flags(session, ctx.actor, patient_id)
