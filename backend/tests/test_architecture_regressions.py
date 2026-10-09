"""Regression tests for the failures reproduced in the architecture review."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
import records_helpers as rh
from audit_helpers import fetch_events_for_patient, wipe_audit_events
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_records_access_rules import _live_permission, _patient, _user

from app.core.actor import Actor
from app.core.authz import Role
from app.core.exceptions import PulseError
from app.core.pagination import encode_cursor
from app.modules.audit import service as audit_service
from app.modules.consent import service as consent_service
from app.modules.consent.models import AccessPermission, BreakGlassAccess
from app.modules.records import repository as records_repo
from app.modules.users import service as users_service
from app.modules.users.models import Patient


@pytest_asyncio.fixture(autouse=True)
async def cleanup(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_audit_events(app_database_url)
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


async def test_provider_cannot_spoof_correct_or_read_an_unrelated_profile(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    login = register_and_login
    await login(email="review-patient@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await login(email="review-a@example.com", role="PROVIDER_STAFF")
    provider_a = await rh.seed_provider_staff(app_database_url, user_email="review-a@example.com")
    eid = await rh.insert_entry(
        app_database_url,
        patient_id=UUID(pid),
        occurred_at=datetime.now(UTC),
        source_provider_id=provider_a,
    )
    await login(email="review-b@example.com", role="PROVIDER_STAFF")
    await rh.seed_provider_staff(
        app_database_url, user_email="review-b@example.com", provider_name="Other hospital"
    )
    assert (await client.get(f"/api/v1/entries/{eid}")).status_code == 404
    assert (await client.get(f"/api/v1/patients/{pid}")).status_code == 404
    body = {
        "entryType": "CLINICAL_NOTE",
        "occurredAt": datetime.now(UTC).isoformat(),
        "text": "Filed by B",
        "sourceProviderId": str(provider_a),
    }
    assert (await client.post(f"/api/v1/patients/{pid}/entries", json=body)).status_code == 403
    body.pop("sourceProviderId")
    assert (
        await client.post(f"/api/v1/patients/{pid}/entries/{eid}/corrections", json=body)
    ).status_code == 404
    assert (await client.post(f"/api/v1/patients/{pid}/entries", json=body)).status_code == 201
    before = await fetch_events_for_patient(app_database_url, UUID(pid))
    assert [e["action"] for e in before] == ["ENTRY_CREATED"]
    await login(email="review-patient@example.com")
    assert (
        await client.get(f"/api/v1/patients/{pid}/analytics/visit-frequency")
    ).status_code == 200
    after = await fetch_events_for_patient(app_database_url, UUID(pid))
    assert [e["action"] for e in after] == ["ENTRY_CREATED", "ANALYTICS_VIEWED"]


async def test_permission_is_rechecked_when_the_statement_executes(
    db_session: AsyncSession, db_engine: AsyncEngine, app_database_url: str
) -> None:
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    await rh.insert_entry(app_database_url, patient_id=patient.id, occurred_at=datetime.now(UTC))
    await _live_permission(
        db_session,
        patient=patient,
        clinician=clinician,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    await db_session.commit()
    stmt = await records_repo.accessible_entries(
        db_session, Actor(user_id=clinician.id, role=Role.CLINICIAN), patient.id
    )
    async with async_sessionmaker(db_engine)() as revoker:
        await revoker.execute(
            delete(AccessPermission).where(AccessPermission.patient_id == patient.id)
        )
        await revoker.commit()
    assert (await db_session.execute(stmt)).scalars().all() == []


@pytest.mark.parametrize("failing_module", ["audit", "notification"])
async def test_emergency_access_rolls_back_if_required_history_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, failing_module: str
) -> None:
    from app.modules.notifications import service as notifications_service

    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    pid = patient.id
    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected required-history failure")

    module = audit_service if failing_module == "audit" else notifications_service
    monkeypatch.setattr(module, "emit" if failing_module == "audit" else "notify", fail)
    with pytest.raises(RuntimeError):
        await consent_service.request_break_glass(db_session, actor, pid, "Emergency regression")
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(BreakGlassAccess)
            .where(BreakGlassAccess.patient_id == pid)
        )
        == 0
    )


async def test_error_contract_and_cross_origin_mutations(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="review-cursor@example.com")
    for path in ["/api/v1/consents", "/api/v1/audit-events", "/api/v1/notifications"]:
        for raw in [
            "not-a-date|not-a-uuid",
            "2025-01-01T00:00:00|00000000-0000-0000-0000-000000000000",
        ]:
            response = await client.get(path, params={"cursor": encode_cursor(raw)})
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    missing = await client.get("/api/v1/nonexistent")
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    denied = await client.post(
        "/api/v1/auth/logout", headers={"Origin": "https://attacker.example"}
    )
    assert denied.status_code == 403
    schema = (await client.get("/openapi.json")).json()
    assert "ErrorCode" in schema["components"]["schemas"]
    assert schema["paths"]["/api/v1/auth/login"]["post"]["responses"]["422"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("/ErrorEnvelope")


async def test_current_lab_trends_exclude_replaced_values(
    db_session: AsyncSession, app_database_url: str
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    await db_session.commit()
    old = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
        value_numeric=99,
    )
    new = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
        value_numeric=5,
    )
    await rh.stamp_superseded(app_database_url, original_id=old, replacement_id=new)
    trend = await records_repo.lab_trend(
        db_session,
        Actor(user_id=owner.id, role=Role.PATIENT),
        patient.id,
        code_system="http://loinc.org",
        code="4548-4",
    )
    assert [p.value_numeric for p in trend] == [5]


async def test_merges_reject_account_conflicts_and_cycles(db_session: AsyncSession) -> None:
    winner = await _patient(db_session, await _user(db_session, Role.PATIENT))
    loser = await _patient(db_session, await _user(db_session, Role.PATIENT))
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    winner_id, loser_id = winner.id, loser.id
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    with pytest.raises(PulseError) as denied:
        await users_service.merge_patients(db_session, actor, winner_id, loser_id)
    assert denied.value.http_status == 409
    loser_to_unclaim = await db_session.get(Patient, loser_id)
    assert loser_to_unclaim is not None
    loser_to_unclaim.user_id = None
    await db_session.commit()
    await users_service.merge_patients(db_session, actor, winner_id, loser_id)
    with pytest.raises(PulseError) as denied:
        await users_service.merge_patients(db_session, actor, loser_id, winner_id)
    assert denied.value.http_status == 409
