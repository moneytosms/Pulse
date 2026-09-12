"""P3.9 (#43) — `GET /notifications` (cursor pagination, api-conventions.md)
and `POST /notifications/{id}/read`.

ASGI-client seam. Rows are seeded by calling `service.notify()` directly
against a short-lived session bound to the same database as `client`
(there is no HTTP endpoint that creates a notification — those come from
other services in a later PR), then every assertion is over HTTP.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, identity_session, wipe_identity
from httpx import AsyncClient

from app.modules.notifications import service
from app.modules.notifications.schemas import NotificationType

_PW = "correct-horse-staple-9"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_identity(app_database_url)


async def _seed(app_database_url: str, user_id: UUID, count: int) -> None:
    async with identity_session(app_database_url) as session:
        for i in range(count):
            await service.notify(
                session, user_id, NotificationType.RECORD_UPLOADED, {"entryId": f"e{i}"}
            )


async def test_cursor_pages_do_not_overlap_or_skip(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="list-cursor@example.com")
    user_id = await rh.user_id_for_email(app_database_url, "list-cursor@example.com")
    await _seed(app_database_url, user_id, 5)

    first = await client.get("/api/v1/notifications?limit=2")
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["nextCursor"]

    # An insert between pages must not shift the window.
    await _seed(app_database_url, user_id, 1)

    second = await client.get(f"/api/v1/notifications?limit=2&cursor={body['nextCursor']}")
    assert second.status_code == 200
    page1 = {i["id"] for i in body["items"]}
    page2 = {i["id"] for i in second.json()["items"]}
    assert page1.isdisjoint(page2)


async def test_invalid_cursor_is_a_validation_error(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="list-bad-cursor@example.com")
    resp = await client.get("/api/v1/notifications?cursor=not-a-real-cursor")
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_mark_read_flips_read_at_and_the_item_stays_listed(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="list-mark-read@example.com")
    user_id = await rh.user_id_for_email(app_database_url, "list-mark-read@example.com")
    await _seed(app_database_url, user_id, 1)

    listing = await client.get("/api/v1/notifications")
    item = listing.json()["items"][0]
    assert item["readAt"] is None

    read = await client.post(f"/api/v1/notifications/{item['id']}/read")
    assert read.status_code == 200
    assert read.json()["readAt"] is not None

    listing_again = await client.get("/api/v1/notifications")
    refreshed = next(i for i in listing_again.json()["items"] if i["id"] == item["id"])
    assert refreshed["readAt"] is not None


async def test_mark_read_on_an_unknown_notification_is_404(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="list-mark-missing@example.com")
    resp = await client.post("/api/v1/notifications/00000000-0000-0000-0000-000000000000/read")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"
