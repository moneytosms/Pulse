"""Notifications HTTP surface — P3.2 (#38) `@stub` endpoints, PROVISIONAL.

Shapes exist so the Phase 3 notification screens can be built ahead of the
service. Real emission and delivery land with the service in P3.9.
"""

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Permission
from app.core.pagination import Page
from app.core.stub import stub
from app.db.session import get_session
from app.modules.auth.dependencies import AuthContext, current_user, requires
from app.modules.notifications.schemas import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationType,
)

router = APIRouter(prefix="/api/v1", tags=["notifications"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]

_STUB_NOTIFICATION = Notification(
    id=UUID("00000000-0000-0000-0000-00000000f001"),
    type=NotificationType.CONSENT_GRANTED,
    title="New consent granted",
    body="Dr Meera Nair can now view your lab reports.",
    read_at=None,
    created_at=datetime(2025, 6, 1, 9, 0, tzinfo=UTC),
)

_STUB_PAGE = Page[Notification](items=[_STUB_NOTIFICATION], next_cursor=None)

_STUB_PREFERENCES = [
    NotificationPreference(
        notification_type=NotificationType.CONSENT_GRANTED,
        channel=NotificationChannel.EMAIL,
        enabled=True,
    ),
    NotificationPreference(
        notification_type=NotificationType.RECORD_UPLOADED,
        channel=NotificationChannel.SMS,
        enabled=False,
    ),
]


@router.get(
    "/notifications",
    dependencies=[requires(Permission.NOTIFICATION_READ_SELF)],
)
@stub(_STUB_PAGE)
async def list_notifications(
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
) -> Page[Notification]:
    return _STUB_PAGE


@router.get(
    "/notification-preferences",
    dependencies=[requires(Permission.NOTIFICATION_PREFERENCES_READ_SELF)],
)
@stub(_STUB_PREFERENCES)
async def list_notification_preferences(
    response: Response,
    ctx: CurrentUser,
    session: SessionDep,
) -> list[NotificationPreference]:
    return _STUB_PREFERENCES
