"""P3.2 (#38) — the notifications `@stub` endpoints.

One test per stub: authenticated request -> 200, `x-pulse-stub: true`,
body parses into the declared schema. Prior art: `test_records_stubs.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

from app.core.pagination import Page
from app.modules.notifications.schemas import Notification, NotificationPreference


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_identity(app_database_url)


async def test_list_notifications_is_a_stub(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="notifications-stub@example.com")
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 200
    assert resp.headers["x-pulse-stub"] == "true"
    Page[Notification].model_validate(resp.json())


async def test_list_notification_preferences_is_a_stub(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="notification-preferences-stub@example.com")
    resp = await client.get("/api/v1/notification-preferences")
    assert resp.status_code == 200
    assert resp.headers["x-pulse-stub"] == "true"
    body = resp.json()
    assert isinstance(body, list)
    for row in body:
        NotificationPreference.model_validate(row)
