"""P3.9 (#43) — per-type/per-channel notification preferences.

ASGI-client seam. Negative test first: a mandatory type must never appear
in the preferences list, and must be rejected outright if a caller tries
to set one — written before `MANDATORY_TYPES` existed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

_MANDATORY = {"BREAK_GLASS_ACCESS", "CONSENT_REVOKED"}
_OPTIONAL = {"CONSENT_GRANTED", "RECORD_UPLOADED", "DAILY_DIGEST"}
_CHANNELS = {"EMAIL", "SMS", "IN_APP"}


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_identity(app_database_url)


async def test_mandatory_types_are_absent_from_the_preferences_list(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="prefs-mandatory@example.com")
    resp = await client.get("/api/v1/notification-preferences")
    assert resp.status_code == 200
    types = {row["notificationType"] for row in resp.json()}
    assert types.isdisjoint(_MANDATORY)


async def test_every_optional_type_and_channel_defaults_to_enabled(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="prefs-defaults@example.com")
    resp = await client.get("/api/v1/notification-preferences")
    assert resp.status_code == 200
    body = resp.json()
    seen = {(row["notificationType"], row["channel"]) for row in body}
    for t in _OPTIONAL:
        for c in _CHANNELS:
            assert (t, c) in seen, f"missing {t}/{c}"
    assert all(row["enabled"] for row in body)


async def test_updating_a_preference_persists_and_is_reflected_on_read(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="prefs-update@example.com")
    put = await client.put(
        "/api/v1/notification-preferences",
        json={"notificationType": "RECORD_UPLOADED", "channel": "EMAIL", "enabled": False},
    )
    assert put.status_code == 200
    assert put.json()["enabled"] is False

    get = await client.get("/api/v1/notification-preferences")
    row = next(
        r
        for r in get.json()
        if r["notificationType"] == "RECORD_UPLOADED" and r["channel"] == "EMAIL"
    )
    assert row["enabled"] is False
    # Untouched rows keep the default.
    other = next(
        r
        for r in get.json()
        if r["notificationType"] == "RECORD_UPLOADED" and r["channel"] == "SMS"
    )
    assert other["enabled"] is True


async def test_a_mandatory_type_cannot_be_set(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="prefs-mandatory-write@example.com")
    resp = await client.put(
        "/api/v1/notification-preferences",
        json={"notificationType": "BREAK_GLASS_ACCESS", "channel": "EMAIL", "enabled": False},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "NOTIFICATION_TYPE_MANDATORY"
