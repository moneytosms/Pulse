"""Audit HTTP surface — P2.0 (#25) `@stub` endpoint, PROVISIONAL.

The Patient's "who accessed my records" view. Real emission and the
filtered projection land in Phase 3 (P3.8).
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
from app.modules.audit.schemas import AuditEventProjection
from app.modules.auth.dependencies import AuthContext, current_user, requires

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]

_STUB_PAGE = Page[AuditEventProjection](
    items=[
        AuditEventProjection(
            id=UUID("00000000-0000-0000-0000-00000000a001"),
            occurred_at=datetime(2025, 6, 10, 14, 5, tzinfo=UTC),
            actor_name="Dr Meera Nair",
            actor_role="CLINICIAN",
            provider_name="Apollo Speciality Hospital",
            action="ENTRY_VIEWED",
            entry_type="LAB_REPORT",
        )
    ],
    next_cursor=None,
)


@router.get("", dependencies=[requires(Permission.AUDIT_READ_SELF)])
@stub(_STUB_PAGE)
async def list_audit_events(
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
    patient_id: Annotated[UUID | None, Query(alias="patientId")] = None,
) -> Page[AuditEventProjection]:
    return _STUB_PAGE
