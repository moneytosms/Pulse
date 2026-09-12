"""Audit HTTP surface — P3.8 (#45).

The Patient's "who accessed my records" view: real emission
(`records/service.py`) and the filtered projection (`audit/service.py`).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.core.pagination import Page
from app.db.session import get_session
from app.modules.audit import service
from app.modules.audit.schemas import AuditEventProjection
from app.modules.auth.dependencies import AuthContext, current_user, requires

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]


@router.get("", dependencies=[requires(Permission.AUDIT_READ_SELF)])
async def list_audit_events(
    ctx: CurrentUser,
    session: SessionDep,
    patient_id: Annotated[UUID | None, Query(alias="patientId")] = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[AuditEventProjection]:
    return await service.list_for_patient(
        session, ctx.actor, patient_id, cursor=cursor, limit=limit
    )
