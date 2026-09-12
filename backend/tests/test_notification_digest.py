"""P3.9 (#43) — the read-computed daily digest for "a clinician viewed
your records" (domain-model.md, "Notifications").

ASGI-client seam: `audit_event` rows are seeded with raw SQL (P3.8, real
emission, hasn't landed), then `GET /notifications` is the read that must
compute the digest. Negative tests first — no views, and a Patient's own
view, must not produce a digest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import notifications_helpers as nh
import pytest_asyncio
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await nh.wipe_audit_events(app_database_url)
    await wipe_identity(app_database_url)


async def _patient_id(client: AsyncClient) -> UUID:
    resp = await client.get("/api/v1/patients/me")
    resp.raise_for_status()
    return UUID(str(resp.json()["id"]))


async def test_no_digest_when_there_are_no_views(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="digest-none@example.com")
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 200
    types = [item["type"] for item in resp.json()["items"]]
    assert "DAILY_DIGEST" not in types


async def test_a_patients_own_view_of_their_own_record_does_not_trigger_a_digest(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="digest-self-view@example.com")
    pid = await _patient_id(client)
    await nh.insert_audit_event(app_database_url, patient_id=pid, actor_role="PATIENT")

    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 200
    types = [item["type"] for item in resp.json()["items"]]
    assert "DAILY_DIGEST" not in types


async def test_a_non_patient_view_produces_exactly_one_digest_notification(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="digest-clinician-view@example.com")
    pid = await _patient_id(client)
    for _ in range(3):
        await nh.insert_audit_event(app_database_url, patient_id=pid, actor_role="CLINICIAN")

    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 200
    digests = [item for item in resp.json()["items"] if item["type"] == "DAILY_DIGEST"]
    assert len(digests) == 1
    assert "3" in digests[0]["body"]


async def test_a_second_read_with_no_new_views_does_not_duplicate_the_digest(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="digest-no-dup@example.com")
    pid = await _patient_id(client)
    await nh.insert_audit_event(app_database_url, patient_id=pid, actor_role="CLINICIAN")

    first = await client.get("/api/v1/notifications")
    assert first.status_code == 200
    first_digests = [item for item in first.json()["items"] if item["type"] == "DAILY_DIGEST"]
    assert len(first_digests) == 1

    second = await client.get("/api/v1/notifications")
    assert second.status_code == 200
    second_digests = [item for item in second.json()["items"] if item["type"] == "DAILY_DIGEST"]
    assert len(second_digests) == 1
    assert second_digests[0]["id"] == first_digests[0]["id"]


async def test_a_view_after_the_last_digest_produces_a_new_digest(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="digest-followup@example.com")
    pid = await _patient_id(client)
    await nh.insert_audit_event(app_database_url, patient_id=pid, actor_role="CLINICIAN")

    first = await client.get("/api/v1/notifications")
    assert first.status_code == 200
    first_digests = [item for item in first.json()["items"] if item["type"] == "DAILY_DIGEST"]
    assert len(first_digests) == 1

    await nh.insert_audit_event(app_database_url, patient_id=pid, actor_role="CLINICIAN")

    second = await client.get("/api/v1/notifications")
    assert second.status_code == 200
    second_digests = [item for item in second.json()["items"] if item["type"] == "DAILY_DIGEST"]
    assert len(second_digests) == 2
