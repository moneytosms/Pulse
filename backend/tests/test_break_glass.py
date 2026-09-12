"""P3.7 (#44) — break-glass: emergency access without Consent.

ASGI-client seam, real Postgres + Redis. Negative first (backend.md): a
blank justification is rejected before any positive grant is exercised.
`get_notification_provider` is overridden onto `FakeNotificationProvider`
(same shape as `test_document_upload.py`'s storage-provider override) so
the mandatory, immediate delivery this endpoint fires can be asserted
without touching real SMTP.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

from app.adapters.notifications import FakeNotificationProvider
from app.main import app
from app.modules.consent.dependencies import get_notification_provider

_PW = "correct-horse-staple-9"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_identity(app_database_url)


@pytest_asyncio.fixture(autouse=True)
async def fake_notification_provider() -> AsyncIterator[FakeNotificationProvider]:
    fake = FakeNotificationProvider()
    app.dependency_overrides[get_notification_provider] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_notification_provider, None)


async def _patient_and_clinician(
    client: AsyncClient,
    register_and_login: RegisterAndLogin,
    *,
    patient_email: str,
    clin_email: str,
) -> tuple[str, str]:
    await register_and_login(email=patient_email)
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await register_and_login(email=clin_email, role="CLINICIAN")
    return pid, ""


async def test_missing_justification_is_422(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p1@example.com",
        clin_email="bg-c1@example.com",
    )
    resp = await client.post(f"/api/v1/patients/{pid}/break-glass", json={})
    assert resp.status_code == 422


async def test_blank_justification_is_422(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p2@example.com",
        clin_email="bg-c2@example.com",
    )
    resp = await client.post(f"/api/v1/patients/{pid}/break-glass", json={"justification": "   "})
    assert resp.status_code == 422


async def test_non_clinician_cannot_request_break_glass(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="bg-p3@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await register_and_login(email="bg-staff3@example.com", role="PROVIDER_STAFF")
    resp = await client.post(
        f"/api/v1/patients/{pid}/break-glass",
        json={"justification": "Patient unresponsive in ED."},
    )
    assert resp.status_code == 403


async def test_valid_break_glass_grants_exactly_sixty_minutes(
    client: AsyncClient,
    register_and_login: RegisterAndLogin,
    fake_notification_provider: FakeNotificationProvider,
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p4@example.com",
        clin_email="bg-c4@example.com",
    )
    before = datetime.now(UTC)
    resp = await client.post(
        f"/api/v1/patients/{pid}/break-glass",
        json={"justification": "Patient unresponsive in ED, no consent on file."},
    )
    after = datetime.now(UTC)
    assert resp.status_code == 201
    body = resp.json()
    assert body["patientId"] == pid

    expires_at = datetime.fromisoformat(body["expiresAt"].replace("Z", "+00:00"))
    assert before + timedelta(minutes=60) <= expires_at <= after + timedelta(minutes=60)


async def test_valid_break_glass_grants_read_access_to_the_timeline(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p5@example.com",
        clin_email="bg-c5@example.com",
    )
    await rh.insert_entry(
        app_database_url,
        patient_id=pid,  # type: ignore[arg-type]
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    denied = await client.get(f"/api/v1/patients/{pid}/entries")
    assert denied.status_code == 404

    grant = await client.post(
        f"/api/v1/patients/{pid}/break-glass",
        json={"justification": "Patient unresponsive in ED, no consent on file."},
    )
    assert grant.status_code == 201

    granted = await client.get(f"/api/v1/patients/{pid}/entries")
    assert granted.status_code == 200
    assert len(granted.json()["items"]) == 1

    await rh.wipe_records(app_database_url)


async def test_break_glass_writes_an_audit_event_the_patient_can_read(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p6@example.com",
        clin_email="bg-c6@example.com",
    )
    resp = await client.post(
        f"/api/v1/patients/{pid}/break-glass",
        json={"justification": "Patient unresponsive in ED, no consent on file."},
    )
    assert resp.status_code == 201

    await register_and_login(email="bg-p6@example.com")
    events = await client.get("/api/v1/audit-events", params={"patientId": pid})
    assert events.status_code == 200
    actions = [e["action"] for e in events.json()["items"]]
    assert "BREAK_GLASS_ACCESS" in actions


async def test_break_glass_notifies_the_patient_immediately_not_via_digest(
    client: AsyncClient,
    register_and_login: RegisterAndLogin,
    fake_notification_provider: FakeNotificationProvider,
) -> None:
    pid, _ = await _patient_and_clinician(
        client,
        register_and_login,
        patient_email="bg-p7@example.com",
        clin_email="bg-c7@example.com",
    )
    resp = await client.post(
        f"/api/v1/patients/{pid}/break-glass",
        json={"justification": "Patient unresponsive in ED, no consent on file."},
    )
    assert resp.status_code == 201

    # Immediate delivery: the mandatory type's email fires synchronously as
    # part of this request, not the Patient's next digest computation.
    sent_types = [call[2] for call in fake_notification_provider.sent]
    assert "BREAK_GLASS_ACCESS" in sent_types

    await register_and_login(email="bg-p7@example.com")
    notifications = await client.get("/api/v1/notifications")
    assert notifications.status_code == 200
    types = [n["type"] for n in notifications.json()["items"]]
    assert "BREAK_GLASS_ACCESS" in types
