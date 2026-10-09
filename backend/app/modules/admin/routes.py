"""Admin HTTP surface (P4.3, #54).

HTTP only — parse, guard, delegate (backend.md). Every route here is
`ADMIN_DUPLICATE_REVIEW`, Administrator-only (ADR-0007). Responses carry
identity fields and entry counts only, never entry content (ADR-0011) —
enforced by `admin.schemas.AdminPatientIdentity` having no field capable
of holding one.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.core.pagination import Page
from app.db.session import get_session
from app.modules.admin import service
from app.modules.admin.schemas import (
    DuplicateReviewCandidate,
    MergeRecord,
    MergeRequest,
    MergeResult,
    NotDuplicateRequest,
)
from app.modules.auth.dependencies import AuthContext, current_user, requires

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]


@router.get(
    "/duplicate-review",
    dependencies=[requires(Permission.ADMIN_DUPLICATE_REVIEW)],
)
async def list_duplicate_review_queue(
    ctx: CurrentUser, session: SessionDep, cursor: str | None = None, limit: int = 50
) -> Page[DuplicateReviewCandidate]:
    return await service.duplicate_review_queue(session, ctx.actor, cursor=cursor, limit=limit)


@router.post(
    "/duplicate-review/not-duplicate",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires(Permission.ADMIN_DUPLICATE_REVIEW)],
)
async def decide_not_duplicate(
    payload: NotDuplicateRequest, ctx: CurrentUser, session: SessionDep
) -> None:
    await service.mark_not_duplicate(session, ctx.actor, payload.patient_id_a, payload.patient_id_b)


@router.post(
    "/duplicate-review/merge",
    status_code=status.HTTP_201_CREATED,
    dependencies=[requires(Permission.ADMIN_DUPLICATE_REVIEW)],
)
async def merge_patients(
    payload: MergeRequest, ctx: CurrentUser, session: SessionDep
) -> MergeResult:
    return await service.merge(
        session, ctx.actor, payload.winner_patient_id, payload.loser_patient_id
    )


@router.get(
    "/merges",
    dependencies=[requires(Permission.ADMIN_DUPLICATE_REVIEW)],
)
async def list_reversible_merges(
    ctx: CurrentUser, session: SessionDep, cursor: str | None = None, limit: int = 50
) -> Page[MergeRecord]:
    return await service.reversible_merges(session, ctx.actor, cursor=cursor, limit=limit)


@router.post(
    "/merges/{merge_id}/reverse",
    dependencies=[requires(Permission.ADMIN_DUPLICATE_REVIEW)],
)
async def reverse_merge(merge_id: UUID, ctx: CurrentUser, session: SessionDep) -> MergeResult:
    return await service.reverse(session, ctx.actor, merge_id)
