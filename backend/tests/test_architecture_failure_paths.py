"""Real-database failure and interleaving checks for the architecture fixes."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
import records_helpers as rh
from audit_helpers import wipe_audit_events
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from test_records_access_rules import _patient, _user

from app.adapters.storage import LocalStorageProvider
from app.core.actor import Actor
from app.core.authz import Role
from app.core.exceptions import PulseError
from app.modules.audit import service as audit_service
from app.modules.consent import service as consent_service
from app.modules.consent.models import AccessPermission, Consent
from app.modules.consent.schemas import ConsentCreate, ConsentPurpose, RevocationRequest
from app.modules.records import repository as records_repository
from app.modules.records.models import ClinicalNote, MedicalDocument
from app.modules.users import service as users_service
from app.modules.users.models import PatientMerge


@pytest_asyncio.fixture(autouse=True)
async def cleanup(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_audit_events(app_database_url)
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


async def test_staff_without_a_provider_cannot_file(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="unassociated-patient@example.com")
    pid = (await client.get("/api/v1/patients/me")).json()["id"]
    await register_and_login(email="unassociated-staff@example.com", role="PROVIDER_STAFF")
    response = await client.post(
        f"/api/v1/patients/{pid}/entries",
        json={
            "entryType": "CLINICAL_NOTE",
            "occurredAt": datetime.now(UTC).isoformat(),
            "text": "Synthetic note",
        },
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "operation,failing_module",
    [("grant", "audit"), ("revoke", "audit"), ("revoke", "notification")],
)
async def test_consent_and_permission_roll_back_when_audit_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, operation: str, failing_module: str
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    pid = patient.id
    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    payload = ConsentCreate(
        grantee_user_id=clinician.id,
        purpose=ConsentPurpose.TREATMENT,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    granted = (
        await consent_service.grant_consent(db_session, actor, payload)
        if operation == "revoke"
        else None
    )

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected audit failure")

    from app.modules.notifications import service as notifications_service

    module = audit_service if failing_module == "audit" else notifications_service
    monkeypatch.setattr(module, "emit" if failing_module == "audit" else "notify", fail)
    with pytest.raises(RuntimeError):
        if granted:
            await consent_service.revoke_consent(db_session, actor, granted.id, RevocationRequest())
        else:
            await consent_service.grant_consent(db_session, actor, payload)
    count = await db_session.scalar(
        select(func.count()).select_from(AccessPermission).where(AccessPermission.patient_id == pid)
    )
    assert count == (1 if operation == "revoke" else 0)
    row = await db_session.scalar(select(Consent).where(Consent.patient_id == pid))
    assert (row is None) if operation == "grant" else (row is not None and row.revoked_at is None)


async def test_failed_upload_removes_bytes_and_database_metadata(
    client: AsyncClient,
    register_and_login: RegisterAndLogin,
    app_database_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    db_session: AsyncSession,
) -> None:
    from app.main import app
    from app.modules.records.dependencies import get_storage_provider

    await register_and_login(email="cleanup-patient@example.com")
    pid = UUID((await client.get("/api/v1/patients/me")).json()["id"])
    await register_and_login(email="cleanup-staff@example.com", role="PROVIDER_STAFF")
    provider_id = await rh.seed_provider_staff(
        app_database_url, user_email="cleanup-staff@example.com"
    )
    eid = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        source_provider_id=provider_id,
        occurred_at=datetime.now(UTC),
    )
    app.dependency_overrides[get_storage_provider] = lambda: LocalStorageProvider(tmp_path)

    async def fail(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected metadata failure")

    monkeypatch.setattr(records_repository, "add_document", fail)
    try:
        response = await client.post(
            f"/api/v1/patients/{pid}/entries/{eid}/documents",
            files={"file": ("report.pdf", b"%PDF-1.4 test", "application/pdf")},
        )
    finally:
        app.dependency_overrides.pop(get_storage_provider, None)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
    assert await db_session.scalar(select(func.count()).select_from(MedicalDocument)) == 0


async def test_opposite_concurrent_merges_cannot_form_a_cycle(
    db_session: AsyncSession, db_engine: AsyncEngine
) -> None:
    first = await _patient(db_session, None)
    second = await _patient(db_session, None)
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    first_id, second_id = first.id, second.id
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def merge(winner: UUID, loser: UUID) -> int:
        async with maker() as session:
            try:
                await users_service.merge_patients(session, actor, winner, loser)
                return 201
            except PulseError as error:
                return error.http_status

    results = await asyncio.gather(merge(first_id, second_id), merge(second_id, first_id))
    assert sorted(results) == [201, 409]
    assert await db_session.scalar(select(func.count()).select_from(PatientMerge)) == 1
    await db_session.refresh(first)
    await db_session.refresh(second)
    assert (first.merged_into_id is None) != (second.merged_into_id is None)


async def test_preexisting_revisions_are_reversible_but_later_corrections_are_not(
    db_session: AsyncSession, app_database_url: str
) -> None:
    winner = await _patient(db_session, None)
    loser = await _patient(db_session, None)
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    winner_id, loser_id = winner.id, loser.id
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    old = await rh.insert_entry(
        app_database_url, patient_id=loser_id, occurred_at=datetime.now(UTC)
    )
    replacement = await rh.insert_entry(
        app_database_url, patient_id=loser_id, occurred_at=datetime.now(UTC)
    )
    await rh.stamp_superseded(app_database_url, original_id=old, replacement_id=replacement)
    merge = await users_service.merge_patients(db_session, actor, winner_id, loser_id)
    await users_service.reverse_merge(db_session, actor, merge.id)
    merge = await users_service.merge_patients(db_session, actor, winner_id, loser_id)
    later = await rh.insert_entry(
        app_database_url, patient_id=winner_id, occurred_at=datetime.now(UTC)
    )
    await rh.stamp_superseded(app_database_url, original_id=replacement, replacement_id=later)
    with pytest.raises(PulseError) as denied:
        await users_service.reverse_merge(db_session, actor, merge.id)
    assert denied.value.http_status == 409


async def test_analytics_rejects_overflow_and_accepts_a_narrower_window(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    for year in (2024, 2025):
        db_session.add(
            ClinicalNote(
                patient_id=patient.id,
                occurred_at=datetime(year, 1, 1, tzinfo=UTC),
                text="Synthetic",
            )
        )
    await db_session.commit()
    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    pid = patient.id
    monkeypatch.setattr(records_repository, "_MAX_SERIES_ROWS", 1)
    with pytest.raises(PulseError) as overflow:
        await records_repository.visit_frequency_by_month(db_session, actor, pid)
    assert overflow.value.code == "ANALYTICS_WINDOW_TOO_LARGE"
    rows = await records_repository.visit_frequency_by_month(
        db_session, actor, pid, from_date=date(2025, 1, 1)
    )
    assert len(rows) == 1 and rows[0].count == 1


async def test_rate_limit_has_an_expiry_and_returns_a_coded_response(client: AsyncClient) -> None:
    from app.core.redis import get_redis

    for _ in range(10):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "missing@example.com", "password": "invalid-password"},
        )
        assert response.status_code == 401
    blocked = await client.post(
        "/api/v1/auth/login", json={"email": "missing@example.com", "password": "invalid-password"}
    )
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match="rate:login-account:*")]
    assert keys and 0 < await redis.ttl(keys[0]) <= 60


@pytest.mark.parametrize("failure", ["missing", "corrupt"])
async def test_unavailable_document_bytes_are_controlled_and_not_logged_as_a_view(
    client: AsyncClient,
    register_and_login: RegisterAndLogin,
    app_database_url: str,
    tmp_path: Path,
    db_session: AsyncSession,
    failure: str,
) -> None:
    import hashlib

    from app.main import app
    from app.modules.audit.models import AuditAction, AuditEvent
    from app.modules.records.dependencies import get_storage_provider

    await register_and_login(email="unavailable-document@example.com")
    pid = UUID((await client.get("/api/v1/patients/me")).json()["id"])
    eid = await rh.insert_entry(app_database_url, patient_id=pid, occurred_at=datetime.now(UTC))
    storage = LocalStorageProvider(tmp_path)
    original = b"%PDF-1.4 synthetic document"
    stored = await storage.put("document.pdf", original, "application/pdf")
    document = MedicalDocument(
        entry_id=eid,
        filename="document.pdf",
        mime_type="application/pdf",
        size_bytes=len(original),
        storage_path=stored,
        checksum_sha256=hashlib.sha256(original).hexdigest(),
    )
    db_session.add(document)
    await db_session.commit()
    did = document.id
    if failure == "missing":
        await storage.delete(stored)
    else:
        await storage.put("document.pdf", b"%PDF-corrupt", "application/pdf")
    app.dependency_overrides[get_storage_provider] = lambda: storage
    try:
        response = await client.get(f"/api/v1/documents/{did}")
    finally:
        app.dependency_overrides.pop(get_storage_provider, None)
    assert response.status_code == (404 if failure == "missing" else 500)
    assert response.json()["error"]["code"] == (
        "NOT_FOUND" if failure == "missing" else "INTERNAL_ERROR"
    )
    assert (
        await db_session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == AuditAction.DOCUMENT_VIEWED,
                AuditEvent.resource_id == did,
            )
        )
        == 0
    )


async def test_readiness_checks_dependencies_while_liveness_stays_available(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.core import readiness

    monkeypatch.setenv("PULSE_UPLOAD_DIR", str(tmp_path))
    assert (await client.get("/api/v1/ready")).status_code == 200

    class UnavailableRedis:
        async def ping(self) -> None:
            raise ConnectionError("injected Redis outage")

    monkeypatch.setattr(readiness, "get_redis", lambda: UnavailableRedis())
    failed = await client.get("/api/v1/ready")
    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_notification_params_reject_clinical_content_before_writing(
    db_session: AsyncSession,
) -> None:
    from pydantic import ValidationError

    from app.modules.notifications import service as notifications_service
    from app.modules.notifications.models import Notification as NotificationRow
    from app.modules.notifications.schemas import NotificationType

    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    await db_session.commit()
    with pytest.raises(ValidationError):
        await notifications_service.notify(
            db_session,
            patient.id,
            NotificationType.RECORD_UPLOADED,
            params={"entryId": "not-an-id", "diagnosis": "Synthetic clinical value"},
        )
    assert await db_session.scalar(select(func.count()).select_from(NotificationRow)) == 0


async def test_merge_rejects_a_losers_live_access_grant(db_session: AsyncSession) -> None:
    winner = await _patient(db_session, None)
    owner = await _user(db_session, Role.PATIENT)
    loser = await _patient(db_session, owner)
    clinician = await _user(db_session, Role.CLINICIAN)
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    from app.modules.consent.models import BreakGlassAccess

    # Imported emergency grants can exist on an unclaimed identity.
    loser.user_id = None
    await db_session.commit()
    db_session.add(
        BreakGlassAccess(
            patient_id=loser.id,
            clinician_user_id=clinician.id,
            justification="Synthetic emergency",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db_session.commit()
    with pytest.raises(PulseError) as denied:
        await users_service.merge_patients(
            db_session, Actor(user_id=admin.id, role=Role.ADMINISTRATOR), winner.id, loser.id
        )
    assert denied.value.http_status == 409


async def test_merge_audit_history_follows_the_live_identity_scope(
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    winner = await _patient(db_session, owner)
    loser = await _patient(db_session, None)
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    patient_actor = Actor(user_id=owner.id, role=Role.PATIENT)
    admin_actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    await audit_service.emit(
        db_session,
        actor=admin_actor,
        action=audit_service.AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=None,
        patient_id=loser.id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    await db_session.commit()
    before = await audit_service.list_for_patient(db_session, patient_actor, winner.id)
    assert not before.items
    merge = await users_service.merge_patients(db_session, admin_actor, winner.id, loser.id)
    after = await audit_service.list_for_patient(db_session, patient_actor, winner.id)
    assert any(row.action == audit_service.AuditAction.ENTRY_VIEWED for row in after.items)
    await users_service.reverse_merge(db_session, admin_actor, merge.id)
    reversed_page = await audit_service.list_for_patient(db_session, patient_actor, winner.id)
    assert not any(
        row.action == audit_service.AuditAction.ENTRY_VIEWED for row in reversed_page.items
    )


async def test_document_added_after_merge_blocks_unsafe_reversal(
    db_session: AsyncSession,
    app_database_url: str,
) -> None:
    from uuid import uuid4

    winner = await _patient(db_session, None)
    loser = await _patient(db_session, None)
    admin = await _user(db_session, Role.ADMINISTRATOR)
    await db_session.commit()
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=loser.id, occurred_at=datetime.now(UTC)
    )
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    merge = await users_service.merge_patients(db_session, actor, winner.id, loser.id)
    db_session.add(
        MedicalDocument(
            id=uuid4(),
            entry_id=entry_id,
            filename="synthetic.pdf",
            mime_type="application/pdf",
            size_bytes=4,
            checksum_sha256="0" * 64,
            storage_path="synthetic",
            uploaded_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    with pytest.raises(PulseError) as denied:
        await users_service.reverse_merge(db_session, actor, merge.id)
    assert denied.value.http_status == 409


async def test_digest_includes_views_committed_after_their_event_timestamp(
    db_session: AsyncSession,
) -> None:
    from app.modules.audit.models import AuditEvent
    from app.modules.notifications import service as notifications_service
    from app.modules.notifications.schemas import NotificationType

    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    await audit_service.emit(
        db_session,
        actor=Actor(user_id=clinician.id, role=Role.CLINICIAN),
        action=audit_service.AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=None,
        patient_id=patient.id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    await db_session.commit()
    first = await notifications_service.list_notifications(db_session, actor)
    digest = next(n for n in first.items if n.type == NotificationType.DAILY_DIGEST)
    assert digest.params.view_count == 1
    # Simulate a view transaction that started before this check but committed
    # afterward. Timestamp-based watermarks permanently miss such a view.
    db_session.add(
        AuditEvent(
            actor_user_id=clinician.id,
            actor_role=Role.CLINICIAN,
            action=audit_service.AuditAction.ENTRY_VIEWED,
            resource_type="medical_entry",
            patient_id=patient.id,
            outcome=audit_service.AuditOutcome.SUCCESS,
            occurred_at=digest.created_at - timedelta(microseconds=1),
            event_metadata={},
        )
    )
    await db_session.commit()
    second = await notifications_service.list_notifications(db_session, actor)
    digests = [n for n in second.items if n.type == NotificationType.DAILY_DIGEST]
    assert len(digests) == 2 and sum(n.params.view_count or 0 for n in digests) == 2
    third = await notifications_service.list_notifications(db_session, actor)
    assert len([n for n in third.items if n.type == NotificationType.DAILY_DIGEST]) == 2
