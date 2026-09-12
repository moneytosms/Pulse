"""Notifications HTTP surface (P3.9, #43).

HTTP only — parse, guard, delegate to `service`. `notify()` itself is not
called from here: it is invoked by the services that raise notifications
(consent grant/revoke, break-glass) which import
`app.modules.notifications.service` directly.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.core.pagination import Page
from app.db.session import get_session
from app.modules.auth.dependencies import AuthContext, current_user, requires
from app.modules.notifications import service
from app.modules.notifications.schemas import Notification, NotificationPreference

router = APIRouter(prefix="/api/v1", tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]


@router.get(
    "/notifications",
    dependencies=[requires(Permission.NOTIFICATION_READ_SELF)],
)
async def list_notifications(
    ctx: CurrentUser,
    session: SessionDep,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[Notification]:
    return await service.list_notifications(session, ctx.actor, cursor=cursor, limit=limit)


@router.post(
    "/notifications/{notification_id}/read",
    dependencies=[requires(Permission.NOTIFICATION_MANAGE_SELF)],
)
async def mark_notification_read(
    notification_id: UUID, ctx: CurrentUser, session: SessionDep
) -> Notification:
    return await service.mark_read(session, ctx.actor, notification_id)


@router.get(
    "/notification-preferences",
    dependencies=[requires(Permission.NOTIFICATION_PREFERENCES_READ_SELF)],
)
async def list_notification_preferences(
    ctx: CurrentUser, session: SessionDep
) -> list[NotificationPreference]:
    return await service.list_preferences(session, ctx.actor)


@router.put(
    "/notification-preferences",
    dependencies=[requires(Permission.NOTIFICATION_MANAGE_SELF)],
)
async def update_notification_preference(
    payload: NotificationPreference, ctx: CurrentUser, session: SessionDep
) -> NotificationPreference:
    return await service.set_preference(session, ctx.actor, payload)
