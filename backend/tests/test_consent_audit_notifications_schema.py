"""P3.1 (#37) — consent, access_permission, audit_event, notification,
notification_preference.

Migration/schema-inspection seam, same shape as test_records_schema.py:
no app, no HTTP. Plus one grant-privilege proof against `pulse_app`
directly (ADR-0008) — the closest prior art for that is migration
0001's docstring, since no earlier migration test exercises the grant
in code; this is the first one that does.

Written red: migration 0005 does not exist yet, so every assertion here
fails until it lands.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

_TABLES = (
    "consent",
    "access_permission",
    "audit_event",
    "notification",
    "notification_preference",
)


def _snapshot(sync_conn: Any) -> dict[str, Any]:
    insp = inspect(sync_conn)
    tables = set(insp.get_table_names())
    out: dict[str, Any] = {"tables": tables, "columns": {}, "fks": {}, "indexes": {}, "pk": {}}
    for t in tables:
        out["columns"][t] = {c["name"]: c for c in insp.get_columns(t)}
        out["fks"][t] = insp.get_foreign_keys(t)
        out["indexes"][t] = insp.get_indexes(t)
        out["pk"][t] = insp.get_pk_constraint(t)
    return out


@pytest_asyncio.fixture
async def schema(db_engine: AsyncEngine) -> dict[str, Any]:
    async with db_engine.connect() as conn:
        return await conn.run_sync(_snapshot)


def test_all_five_tables_exist(schema: dict[str, Any]) -> None:
    assert set(_TABLES) <= schema["tables"], sorted(set(_TABLES) - schema["tables"])


def _fk_indexed(schema: dict[str, Any], table: str, column: str) -> bool:
    indexed_cols = {c for ix in schema["indexes"][table] for c in ix["column_names"]}
    pk_cols = set(schema["pk"][table]["constrained_columns"])
    return column in indexed_cols or column in pk_cols


@pytest.mark.parametrize(
    "table,column",
    [
        ("consent", "patient_id"),
        ("consent", "grantee_user_id"),
        ("access_permission", "consent_id"),
        ("access_permission", "patient_id"),
        ("access_permission", "grantee_user_id"),
        ("audit_event", "actor_user_id"),
        ("audit_event", "patient_id"),
        ("notification", "user_id"),
        ("notification_preference", "user_id"),
    ],
)
def test_every_fk_is_indexed(schema: dict[str, Any], table: str, column: str) -> None:
    assert _fk_indexed(schema, table, column), f"{table}.{column} has no index"


def test_access_permission_consent_id_is_unique(schema: dict[str, Any]) -> None:
    unique_single_col = {
        tuple(ix["column_names"])
        for ix in schema["indexes"]["access_permission"]
        if ix.get("unique")
    }
    assert ("consent_id",) in unique_single_col


def test_no_clinical_columns_leak_into_these_tables(schema: dict[str, Any]) -> None:
    banned = {"diagnosis", "medication_name", "value_numeric", "note_text", "value_text"}
    for table in _TABLES:
        cols = set(schema["columns"][table])
        assert cols.isdisjoint(banned), f"{table} has clinical-looking columns: {cols & banned}"


async def test_audit_event_app_role_cannot_update(app_database_url: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(app_database_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError, match="(?i)permission denied"):
                await conn.execute(
                    text("UPDATE audit_event SET outcome = outcome WHERE false")
                )
    finally:
        await engine.dispose()


async def test_audit_event_app_role_cannot_delete(app_database_url: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(app_database_url)
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError, match="(?i)permission denied"):
                await conn.execute(text("DELETE FROM audit_event WHERE false"))
    finally:
        await engine.dispose()


async def test_audit_event_app_role_can_insert_and_select(
    db_session: AsyncSession,
) -> None:
    from app.core.authz import Role
    from app.modules.audit.models import AuditAction, AuditEvent, AuditOutcome
    from app.modules.users.models import Patient, Provider, ProviderKind, User

    user = User(
        email=f"audit-model-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=Role.PATIENT,
    )
    provider = Provider(name="Test Provider", kind=ProviderKind.HOSPITAL, city="c", state="s")
    db_session.add_all([user, provider])
    await db_session.flush()
    patient = Patient(user_id=user.id, full_name="Test Patient")
    db_session.add(patient)
    await db_session.flush()

    event = AuditEvent(
        actor_user_id=user.id,
        actor_role=Role.PATIENT,
        action=AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=None,
        patient_id=patient.id,
        outcome=AuditOutcome.SUCCESS,
    )
    db_session.add(event)
    await db_session.commit()

    from sqlalchemy import select

    fetched = (
        await db_session.execute(select(AuditEvent).where(AuditEvent.id == event.id))
    ).scalar_one()
    assert fetched.action == AuditAction.ENTRY_VIEWED
    assert fetched.event_metadata == {}


async def test_consent_access_permission_notification_round_trip(
    db_session: AsyncSession,
) -> None:
    from app.core.authz import Role
    from app.modules.consent.models import AccessPermission, Consent
    from app.modules.consent.schemas import ConsentPurpose
    from app.modules.notifications.models import Notification, NotificationPreference
    from app.modules.notifications.schemas import NotificationChannel, NotificationType
    from app.modules.users.models import Patient, User

    patient_user = User(
        email=f"rt-patient-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=Role.PATIENT,
    )
    clinician_user = User(
        email=f"rt-clinician-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=Role.CLINICIAN,
    )
    db_session.add_all([patient_user, clinician_user])
    await db_session.flush()
    patient = Patient(user_id=patient_user.id, full_name="RT Patient")
    db_session.add(patient)
    await db_session.flush()

    now = datetime.now(UTC)
    consent = Consent(
        patient_id=patient.id,
        grantee_user_id=clinician_user.id,
        entry_types=["LAB_REPORT"],
        purpose=ConsentPurpose.TREATMENT,
        expires_at=now + timedelta(days=30),
    )
    db_session.add(consent)
    await db_session.flush()

    permission = AccessPermission(
        consent_id=consent.id,
        patient_id=patient.id,
        grantee_user_id=clinician_user.id,
        entry_types=["LAB_REPORT"],
        expires_at=consent.expires_at,
    )
    db_session.add(permission)

    notification = Notification(
        user_id=patient_user.id,
        type=NotificationType.CONSENT_GRANTED,
        params={"consent_id": str(consent.id)},
    )
    db_session.add(notification)

    preference = NotificationPreference(
        user_id=patient_user.id,
        notification_type=NotificationType.RECORD_UPLOADED,
        channel=NotificationChannel.EMAIL,
        enabled=False,
    )
    db_session.add(preference)

    await db_session.commit()

    assert permission.id is not None
    assert notification.id is not None
    assert preference.id is not None


async def test_access_permission_consent_id_unique_constraint_enforced(
    db_session: AsyncSession,
) -> None:
    from app.core.authz import Role
    from app.modules.consent.models import AccessPermission, Consent
    from app.modules.consent.schemas import ConsentPurpose
    from app.modules.users.models import Patient, User

    patient_user = User(
        email=f"dup-patient-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=Role.PATIENT,
    )
    clinician_user = User(
        email=f"dup-clinician-{uuid.uuid4()}@example.com",
        password_hash="x",
        role=Role.CLINICIAN,
    )
    db_session.add_all([patient_user, clinician_user])
    await db_session.flush()
    patient = Patient(user_id=patient_user.id, full_name="Dup Patient")
    db_session.add(patient)
    await db_session.flush()

    now = datetime.now(UTC)
    consent = Consent(
        patient_id=patient.id,
        grantee_user_id=clinician_user.id,
        purpose=ConsentPurpose.TREATMENT,
        expires_at=now + timedelta(days=30),
    )
    db_session.add(consent)
    await db_session.flush()

    db_session.add(
        AccessPermission(
            consent_id=consent.id,
            patient_id=patient.id,
            grantee_user_id=clinician_user.id,
            expires_at=consent.expires_at,
        )
    )
    await db_session.commit()

    db_session.add(
        AccessPermission(
            consent_id=consent.id,
            patient_id=patient.id,
            grantee_user_id=clinician_user.id,
            expires_at=consent.expires_at,
        )
    )
    with pytest.raises(DBAPIError, match="(?i)unique"):
        await db_session.commit()
