"""#47, P3.11 — the adversarial suite. All green here is the Phase 3 gate
(domain-model.md, "Enforcement"): every read composes from
`accessible_entries`, so this file is written against the HTTP surface,
the same seam a real attacker (or a real Clinician who should not have
access) would use.

Each test below maps to one bullet of #47's acceptance criteria. Several
are already proven, more thoroughly, at the repository/service seam by
earlier Phase 3 work — this file does not re-derive those, it points at
them, so the whole gate stays legible from one place:

- Revoked consent returns nothing, including mid-session:
  `test_consent_service.py::test_revoke_takes_effect_for_a_session_already_reading`
- Expired consent returns nothing:
  `test_records_access_rules.py::test_clinician_with_expired_permission_sees_nothing`
- The audit `GRANT` rejects `UPDATE`/`DELETE` from the application role:
  `test_consent_audit_notifications_schema.py::test_audit_event_app_role_cannot_{update,delete}`
- No permission decision is cached anywhere, proven by revoking mid-session:
  same as "revoked consent", above — the delete-not-a-cache mechanism.
- Break-glass writes `BREAK_GLASS_ACCESS` (this project's "loud" event —
  see that module's docstring for why there is no separate severity
  column) and notifies the Patient immediately:
  `test_break_glass.py::test_break_glass_grant_emits_audit_and_notifies_patient`
  (or equivalent — see that file for the exact assertions).

What's new here — genuinely end-to-end checks nothing else exercises:
Administrator gets nothing on every clinical endpoint (RBAC-level, before
`accessible_entries` is ever reached); an unauthorised Clinician gets 404
never 403 (past RBAC, denied by the query builder); and a real
entry-type-scoped Consent, granted through the actual API rather than
inserted by hand, does not leak an out-of-scope entry.
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
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


@pytest_asyncio.fixture(autouse=True)
async def _fake_notifications() -> AsyncIterator[None]:
    app.dependency_overrides[get_notification_provider] = FakeNotificationProvider
    yield
    app.dependency_overrides.pop(get_notification_provider, None)


async def test_administrator_gets_nothing_on_every_clinical_endpoint(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    """ADR-0007: an Administrator holds no clinical Permission at all, so
    every one of these is stopped by the route guard before
    `accessible_entries` is ever consulted — 403, never a 200 with data."""
    await register_and_login(email="adv-patient@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await register_and_login(email="adv-admin@example.com", role="ADMINISTRATOR")

    timeline = await client.get(f"/api/v1/patients/{pid}/entries")
    assert timeline.status_code == 403

    detail = await client.get(f"/api/v1/entries/{entry_id}")
    assert detail.status_code == 403

    audit = await client.get("/api/v1/audit-events", params={"patientId": pid})
    assert audit.status_code == 403


async def test_unauthorised_clinician_gets_404_never_403(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    """A Clinician holds `RECORDS_READ` at the role level (they might have
    Consent for *some* Patient), so the route guard lets them through —
    the denial for *this* Patient must come from `accessible_entries` as a
    404, never a 403 that would confirm the record exists
    (clinical-safety.md)."""
    await register_and_login(email="adv-patient-2@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await register_and_login(email="adv-clinician@example.com", role="CLINICIAN")

    timeline = await client.get(f"/api/v1/patients/{pid}/entries")
    assert timeline.status_code == 404

    detail = await client.get(f"/api/v1/entries/{entry_id}")
    assert detail.status_code == 404


async def test_lab_scoped_consent_granted_through_the_real_api_does_not_leak_a_note(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    """Same claim as `test_records_access_rules.py`'s repository-level
    version, but end-to-end: the Consent is granted through the actual
    `POST /api/v1/consents` route (step-up and all), not constructed by
    hand — proving the whole path, service included, honours the scope."""
    await register_and_login(email="adv-patient-3@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    lab_entry = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
    )
    note_entry = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
        entry_type="CLINICAL_NOTE",
    )
    await register_and_login(email="adv-clinician-2@example.com", role="CLINICIAN")
    clin_id = str(
        await rh.user_id_for_email(app_database_url, "adv-clinician-2@example.com")
    )
    await register_and_login(email="adv-patient-3@example.com")
    await client.post("/api/v1/auth/step-up", json={"password": _PW})
    grant = await client.post(
        "/api/v1/consents",
        json={
            "granteeUserId": clin_id,
            "entryTypes": ["LAB_REPORT"],
            "purpose": "TREATMENT",
            "expiresAt": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
        },
    )
    assert grant.status_code == 200

    await register_and_login(email="adv-clinician-2@example.com")
    timeline = await client.get(f"/api/v1/patients/{pid}/entries")
    assert timeline.status_code == 200
    ids = {item["id"] for item in timeline.json()["items"]}
    assert ids == {str(lab_entry)}
    assert str(note_entry) not in ids

    denied = await client.get(f"/api/v1/entries/{note_entry}")
    assert denied.status_code == 404
