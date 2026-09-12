"""P3.6 (#42) — consent grant/revoke/list.

ASGI-client seam, real Postgres + Redis. Negative first (backend.md):
grant requires step-up and rejects an out-of-range expiry before any
positive case is exercised. The concurrency proof — a Clinician session
already reading via consent loses access on its very next read the
instant the Patient revokes, no cache, no delay — is the whole point of
clinical-safety.md's "never cache a permission decision".
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import ASGITransport, AsyncClient

from app.adapters.notifications import FakeNotificationProvider
from app.main import app
from app.modules.consent.dependencies import get_notification_provider

_PW = "correct-horse-staple-9"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


@pytest_asyncio.fixture(autouse=True)
async def _fake_notifications() -> AsyncIterator[None]:
    """Revoke's mandatory `CONSENT_REVOKED` notify() attempts an immediate
    email; real SMTP has nowhere to resolve in the test environment (same
    reasoning as `test_break_glass.py`'s override)."""
    app.dependency_overrides[get_notification_provider] = FakeNotificationProvider
    yield
    app.dependency_overrides.pop(get_notification_provider, None)


def _grant_body(grantee_user_id: str, **overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "granteeUserId": grantee_user_id,
        "purpose": "TREATMENT",
        "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
    }
    body.update(overrides)
    return body


def _second_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _clinician_client(email: str) -> AsyncClient:
    """A second, independently-cookied client logged in as an
    already-registered Clinician — for proving a session that read via
    consent loses access without needing to re-log-in on the shared
    `client` fixture (which would clobber the Patient's own session)."""
    other = _second_client()
    resp = await other.post("/api/v1/auth/login", json={"email": email, "password": _PW})
    resp.raise_for_status()
    return other


async def test_grant_without_step_up_is_rejected(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="consent-nostepup@example.com")
    await register_and_login(email="consent-clin-a@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-a@example.com"))
    await register_and_login(email="consent-nostepup@example.com")  # back to Patient, no step-up

    resp = await client.post("/api/v1/consents", json=_grant_body(clin_id))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "STEP_UP_REQUIRED"


async def test_grant_with_expiry_below_one_day_is_rejected(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="consent-shortexp@example.com")
    await register_and_login(email="consent-clin-b@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-b@example.com"))
    await register_and_login(email="consent-shortexp@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})

    too_soon = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    resp = await client.post("/api/v1/consents", json=_grant_body(clin_id, expiresAt=too_soon))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONSENT_EXPIRY_OUT_OF_RANGE"


async def test_grant_with_expiry_beyond_365_days_is_rejected(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="consent-longexp@example.com")
    await register_and_login(email="consent-clin-c@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-c@example.com"))
    await register_and_login(email="consent-longexp@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})

    too_far = (datetime.now(UTC) + timedelta(days=366)).isoformat()
    resp = await client.post("/api/v1/consents", json=_grant_body(clin_id, expiresAt=too_far))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "CONSENT_EXPIRY_OUT_OF_RANGE"


async def test_grant_with_step_up_creates_a_live_permission(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="consent-grant-ok@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await register_and_login(email="consent-clin-d@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-d@example.com"))
    await register_and_login(email="consent-grant-ok@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})

    resp = await client.post("/api/v1/consents", json=_grant_body(clin_id))
    assert resp.status_code == 200
    body = resp.json()
    assert body["patientId"] == pid
    assert body["granteeUserId"] == clin_id
    assert body["status"] == "ACTIVE"

    listing = await client.get("/api/v1/consents", params={"patientId": pid})
    assert listing.status_code == 200
    assert [c["id"] for c in listing.json()["items"]] == [body["id"]]


async def test_revoke_requires_no_step_up(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    """Revoke works on a plain session — no step-up performed at all."""
    await register_and_login(email="consent-revoke-nostepup@example.com")
    await register_and_login(email="consent-clin-e@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-e@example.com"))
    await register_and_login(email="consent-revoke-nostepup@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})
    consent_id = (await client.post("/api/v1/consents", json=_grant_body(clin_id))).json()["id"]

    # Fresh login, deliberately without a step-up window this time.
    await register_and_login(email="consent-revoke-nostepup@example.com")
    resp = await client.post(f"/api/v1/consents/{consent_id}/revocation", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "REVOKED"


async def test_revoke_takes_effect_for_a_session_already_reading(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    """The negative test: grant, read successfully as the Clinician,
    revoke as the Patient, read again on the SAME Clinician session — 404,
    not a stale 200. `access_permission`'s delete is the mechanism, not a
    cache with a TTL (clinical-safety.md)."""
    await register_and_login(email="consent-live@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await register_and_login(email="consent-clin-f@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-f@example.com"))
    await register_and_login(email="consent-live@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})
    consent_id = (await client.post("/api/v1/consents", json=_grant_body(clin_id))).json()["id"]

    clinician = await _clinician_client("consent-clin-f@example.com")
    try:
        before = await clinician.get(f"/api/v1/patients/{pid}/entries")
        assert before.status_code == 200
        assert len(before.json()["items"]) == 1

        revoke = await client.post(f"/api/v1/consents/{consent_id}/revocation", json={})
        assert revoke.status_code == 200

        after = await clinician.get(f"/api/v1/patients/{pid}/entries")
        assert after.status_code == 404
    finally:
        await clinician.aclose()


async def test_revoke_of_someone_elses_consent_is_404(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="consent-owner@example.com")
    await register_and_login(email="consent-clin-g@example.com", role="CLINICIAN")
    clin_id = str(await rh.user_id_for_email(app_database_url, "consent-clin-g@example.com"))
    await register_and_login(email="consent-owner@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})
    consent_id = (await client.post("/api/v1/consents", json=_grant_body(clin_id))).json()["id"]

    await register_and_login(email="consent-stranger@example.com")
    resp = await client.post(f"/api/v1/consents/{consent_id}/revocation", json={})
    assert resp.status_code == 404
