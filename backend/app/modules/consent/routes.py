"""Consent + break-glass HTTP surface (P3.6/P3.7, #42/#44).

HTTP only — parse, guard, delegate to `service`. Grant is step-up gated
(`requires_step_up()`); revoke is not — withdrawing access is the
frictionless direction (clinical-safety.md). Consent-denied reads
elsewhere in the API surface as 404, never 403; this router's own guards
are the coarse role/permission gate (`requires(...)`), not that rule —
Patient-scoped consent ownership is checked in `service`.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.notifications import NotificationProvider
from app.core.authz import Permission
from app.core.pagination import Page
from app.db.session import get_session
from app.modules.auth.dependencies import (
    AuthContext,
    current_user,
    requires,
    requires_step_up,
)
from app.modules.consent import service
from app.modules.consent.dependencies import get_notification_provider
from app.modules.consent.schemas import (
    BreakGlassGrant,
    BreakGlassRequest,
    Consent,
    ConsentCreate,
    RevocationRequest,
)

router = APIRouter(prefix="/api/v1", tags=["consent"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]
NotificationProviderDep = Annotated[NotificationProvider, Depends(get_notification_provider)]


@router.get(
    "/consents",
    dependencies=[requires(Permission.CONSENT_READ_SELF)],
)
async def list_consents(
    ctx: CurrentUser,
    session: SessionDep,
    patient_id: Annotated[UUID | None, Query(alias="patientId")] = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[Consent]:
    return await service.list_consents(session, ctx.actor, patient_id, cursor=cursor, limit=limit)


@router.post(
    "/consents",
    dependencies=[requires(Permission.CONSENT_MANAGE_SELF), requires_step_up()],
)
async def grant_consent(payload: ConsentCreate, ctx: CurrentUser, session: SessionDep) -> Consent:
    return await service.grant_consent(session, ctx.actor, payload)


@router.post(
    "/consents/{consent_id}/revocation",
    dependencies=[requires(Permission.CONSENT_MANAGE_SELF)],
)
async def revoke_consent(
    consent_id: UUID,
    payload: RevocationRequest,
    ctx: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    provider: NotificationProviderDep,
) -> Consent:
    return await service.revoke_consent(
        session,
        ctx.actor,
        consent_id,
        payload,
        provider=provider,
        background_tasks=background_tasks,
    )


@router.post(
    "/patients/{patient_id}/break-glass",
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires(Permission.BREAK_GLASS_REQUEST)],
)
async def request_break_glass(
    patient_id: UUID,
    payload: BreakGlassRequest,
    ctx: CurrentUser,
    session: SessionDep,
    background_tasks: BackgroundTasks,
    provider: NotificationProviderDep,
) -> BreakGlassGrant:
    return await service.request_break_glass(
        session,
        ctx.actor,
        patient_id,
        payload.justification,
        provider=provider,
        background_tasks=background_tasks,
    )
