"""Consent HTTP surface — P2.0 (#25) `@stub` endpoints, PROVISIONAL.

Shapes exist so the Phase 3 consent screens can be built ahead of the
service. Step-up on grant and the real revoke-without-step-up asymmetry
land with the service in P3.6.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.core.pagination import Page
from app.core.stub import stub
from app.db.session import get_session
from app.modules.auth.dependencies import AuthContext, current_user, requires
from app.modules.consent.schemas import (
    Consent,
    ConsentCreate,
    ConsentPurpose,
    ConsentStatus,
    RevocationRequest,
)

router = APIRouter(prefix="/api/v1/consents", tags=["consent"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]

_STUB_CONSENT = Consent(
    id=UUID("00000000-0000-0000-0000-0000000c0001"),
    patient_id=UUID("00000000-0000-0000-0000-0000000000aa"),
    grantee_user_id=UUID("00000000-0000-0000-0000-0000000000cc"),
    grantee_name="Dr Meera Nair",
    entry_types=["LAB_REPORT", "DIAGNOSIS"],
    from_date=None,
    to_date=None,
    purpose=ConsentPurpose.TREATMENT,
    purpose_text=None,
    status=ConsentStatus.ACTIVE,
    expires_at=datetime(2025, 12, 31, tzinfo=UTC),
    granted_at=datetime(2025, 6, 1, tzinfo=UTC),
)

_STUB_PAGE = Page[Consent](items=[_STUB_CONSENT], next_cursor=None)


@router.get("", dependencies=[requires(Permission.CONSENT_READ_SELF)])
@stub(_STUB_PAGE)
async def list_consents(
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
    patient_id: Annotated[UUID | None, Query(alias="patientId")] = None,
) -> Page[Consent]:
    return _STUB_PAGE


@router.post("", dependencies=[requires(Permission.CONSENT_MANAGE_SELF)])
@stub(_STUB_CONSENT)
async def grant_consent(
    payload: ConsentCreate,
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
) -> Consent:
    return _STUB_CONSENT


@router.post(
    "/{consent_id}/revocation",
    dependencies=[requires(Permission.CONSENT_MANAGE_SELF)],
)
@stub(_STUB_CONSENT)
async def revoke_consent(
    consent_id: UUID,
    payload: RevocationRequest,
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
) -> Consent:
    return _STUB_CONSENT
