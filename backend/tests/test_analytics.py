"""P4.2 (#53) — analytics queries composed from `accessible_entries`.

Repository/service-level, real Postgres, no HTTP. Negative test first
(backend.md): an actor unrelated to the Patient gets an empty series
from every function here, exactly like `accessible_entries` itself —
because that is what each of these composes from (ADR-0006). A
positive-only suite would pass just as happily if a function quietly
switched to a raw, unfiltered query.

The identity data-quality flags are additionally actor-gated in the
service itself (P4.2 security review): Administrator or the Patient's
own User only — the negative case here is a denial, not an empty list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.modules.analytics import service as analytics_service
from app.modules.analytics.schemas import DataQualityFlag
from app.modules.records.models import Diagnosis, LabReport, Prescription
from app.modules.users.models import Patient, Provider, ProviderKind, User

_PW_HASH = "x"


async def _user(db_session: AsyncSession, role: Role = Role.PATIENT) -> User:
    user = User(
        email=f"{role.value.lower()}-{uuid.uuid4()}@example.com",
        password_hash=_PW_HASH,
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _patient(db_session: AsyncSession, user: User | None, **fields: object) -> Patient:
    patient = Patient(user_id=user.id if user else None, full_name="Test Patient", **fields)
    db_session.add(patient)
    await db_session.flush()
    return patient


async def _provider(db_session: AsyncSession, name: str = "Test Provider") -> Provider:
    provider = Provider(name=name, kind=ProviderKind.HOSPITAL, city="Chennai", state="Tamil Nadu")
    db_session.add(provider)
    await db_session.flush()
    return provider


async def test_unrelated_actor_gets_empty_series_everywhere(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    entry = LabReport(
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        code_system="LOINC",
        code="2345-7",
        display_name="Glucose",
        value_numeric=95,
    )
    db_session.add(entry)
    await db_session.commit()

    stranger = await _user(db_session)
    actor = Actor(user_id=stranger.id, role=Role.PATIENT)

    assert (
        await analytics_service.lab_trend(
            db_session, actor, patient.id, code_system="LOINC", code="2345-7"
        )
        == []
    )
    assert await analytics_service.visit_frequency_by_month(db_session, actor, patient.id) == []
    assert await analytics_service.active_medications(db_session, actor, patient.id) == []
    assert await analytics_service.provider_entry_counts(db_session, actor, patient.id) == []
    # Identity flags are gated (P4.2 security review): a stranger's patient_id
    # is a capability probe, so data_quality_flags denies before anything reads.
    with pytest.raises(PulseError) as denied:
        await analytics_service.data_quality_flags(db_session, actor, patient.id)
    assert denied.value.code is ErrorCode.FORBIDDEN


async def test_identity_flags_denied_for_unrelated_and_clinician_actors(
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    stranger = await _user(db_session)
    clinician = await _user(db_session, Role.CLINICIAN)

    with pytest.raises(PulseError) as stranger_denied:
        await analytics_service.identity_data_quality_flags(
            db_session, Actor(user_id=stranger.id, role=Role.PATIENT), patient.id
        )
    assert stranger_denied.value.code is ErrorCode.FORBIDDEN

    with pytest.raises(PulseError) as clinician_denied:
        await analytics_service.identity_data_quality_flags(
            db_session, Actor(user_id=clinician.id, role=Role.CLINICIAN), patient.id
        )
    assert clinician_denied.value.code is ErrorCode.FORBIDDEN


async def test_identity_flags_unclaimed_patient_readable_by_admin_only(
    db_session: AsyncSession,
) -> None:
    # Provider-filed, never claimed: no user_id, so no self path exists —
    # only the Administrator data-quality queue may read its flags. Identity
    # fields are complete, so the admin sees no flags at all.
    patient = await _patient(
        db_session, None, date_of_birth=date(1970, 1, 1), phone="+91 90000 00004"
    )
    admin = await _user(db_session, Role.ADMINISTRATOR)
    staff = await _user(db_session, Role.PROVIDER_STAFF)

    admin_actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    assert (
        await analytics_service.identity_data_quality_flags(db_session, admin_actor, patient.id)
        == []
    )

    with pytest.raises(PulseError) as staff_denied:
        await analytics_service.identity_data_quality_flags(
            db_session, Actor(user_id=staff.id, role=Role.PROVIDER_STAFF), patient.id
        )
    assert staff_denied.value.code is ErrorCode.FORBIDDEN


async def test_lab_trend_returns_only_matching_code_in_order(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    db_session.add_all(
        [
            LabReport(
                patient_id=patient.id,
                occurred_at=datetime(2025, 3, 1, tzinfo=UTC),
                code_system="LOINC",
                code="2345-7",
                display_name="Glucose",
                value_numeric=110,
            ),
            LabReport(
                patient_id=patient.id,
                occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
                code_system="LOINC",
                code="2345-7",
                display_name="Glucose",
                value_numeric=95,
            ),
            LabReport(
                patient_id=patient.id,
                occurred_at=datetime(2025, 2, 1, tzinfo=UTC),
                code_system="LOINC",
                code="789-8",
                display_name="RBC",
                value_numeric=4.8,
            ),
        ]
    )
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    points = await analytics_service.lab_trend(
        db_session, actor, patient.id, code_system="LOINC", code="2345-7"
    )

    assert [p.value_numeric for p in points] == [95, 110]
    assert points[0].occurred_at < points[1].occurred_at


async def test_visit_frequency_groups_by_month_and_excludes_superseded(
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    jan_a = Diagnosis(
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 5, tzinfo=UTC),
        code_system="SNOMED-CT",
        code="44054006",
        display_name="Type 2 diabetes mellitus",
    )
    jan_b = Diagnosis(
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 20, tzinfo=UTC),
        code_system="SNOMED-CT",
        code="38341003",
        display_name="Hypertension",
    )
    feb = Diagnosis(
        patient_id=patient.id,
        occurred_at=datetime(2025, 2, 1, tzinfo=UTC),
        code_system="SNOMED-CT",
        code="195967001",
        display_name="Asthma",
    )
    db_session.add_all([jan_a, jan_b, feb])
    await db_session.flush()
    jan_a.superseded_by_id = jan_b.id
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    counts = await analytics_service.visit_frequency_by_month(db_session, actor, patient.id)

    assert {(c.month, c.count) for c in counts} == {(date(2025, 1, 1), 1), (date(2025, 2, 1), 1)}


async def test_active_medications_excludes_superseded(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    old = Prescription(
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        medication_name="Metformin 500mg",
    )
    current = Prescription(
        patient_id=patient.id,
        occurred_at=datetime(2025, 2, 1, tzinfo=UTC),
        medication_name="Metformin 1000mg",
    )
    db_session.add_all([old, current])
    await db_session.flush()
    old.superseded_by_id = current.id
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    meds = await analytics_service.active_medications(db_session, actor, patient.id)

    assert [m.medication_name for m in meds] == ["Metformin 1000mg"]


async def test_provider_entry_counts_groups_by_provider(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner)
    provider_a = await _provider(db_session, "Apollo")
    provider_b = await _provider(db_session, "Fortis")
    db_session.add_all(
        [
            Diagnosis(
                patient_id=patient.id,
                source_provider_id=provider_a.id,
                occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
                code_system="SNOMED-CT",
                code="44054006",
                display_name="Type 2 diabetes mellitus",
            ),
            Diagnosis(
                patient_id=patient.id,
                source_provider_id=provider_a.id,
                occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
                code_system="SNOMED-CT",
                code="38341003",
                display_name="Hypertension",
            ),
            Diagnosis(
                patient_id=patient.id,
                source_provider_id=provider_b.id,
                occurred_at=datetime(2025, 1, 3, tzinfo=UTC),
                code_system="SNOMED-CT",
                code="195967001",
                display_name="Asthma",
            ),
        ]
    )
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    counts = await analytics_service.provider_entry_counts(db_session, actor, patient.id)

    assert {(c.provider_id, c.count) for c in counts} == {
        (provider_a.id, 2),
        (provider_b.id, 1),
    }


async def test_data_quality_flags_clean_patient_has_none(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(
        db_session, owner, date_of_birth=date(1990, 1, 1), phone="+91 90000 00001"
    )
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    assert await analytics_service.data_quality_flags(db_session, actor, patient.id) == []


async def test_data_quality_flags_missing_dob_and_contact(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(db_session, owner, date_of_birth=None, phone=None)
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    flags = await analytics_service.data_quality_flags(db_session, actor, patient.id)

    assert DataQualityFlag.MISSING_DOB in flags
    assert DataQualityFlag.MISSING_CONTACT in flags


async def test_data_quality_flags_implausible_dob() -> None:
    from app.modules.analytics.service import _implausible_dob

    assert _implausible_dob(date.today() + timedelta(days=1)) is True
    assert _implausible_dob(date(1850, 1, 1)) is True
    assert _implausible_dob(date(1990, 1, 1)) is False


async def test_data_quality_flags_unclaimed_long_lived(db_session: AsyncSession) -> None:
    patient = Patient(
        user_id=None,
        full_name="Never Claimed",
        date_of_birth=date(1970, 1, 1),
        phone="+91 90000 00002",
    )
    db_session.add(patient)
    await db_session.flush()
    # created_at has a server default of now(); backdate it directly so the
    # "long-lived" window is actually exercised.
    from sqlalchemy import update

    await db_session.execute(
        update(Patient)
        .where(Patient.id == patient.id)
        .values(created_at=datetime.now(UTC) - timedelta(days=400))
    )
    await db_session.commit()

    admin = await _user(db_session, Role.ADMINISTRATOR)
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)
    flags = await analytics_service.data_quality_flags(db_session, actor, patient.id)

    assert DataQualityFlag.UNCLAIMED_LONG_LIVED in flags


async def test_data_quality_flags_future_dated_entry(db_session: AsyncSession) -> None:
    owner = await _user(db_session)
    patient = await _patient(
        db_session, owner, date_of_birth=date(1990, 1, 1), phone="+91 90000 00003"
    )
    entry = Diagnosis(
        patient_id=patient.id,
        occurred_at=datetime.now(UTC) + timedelta(days=30),
        code_system="SNOMED-CT",
        code="44054006",
        display_name="Type 2 diabetes mellitus",
    )
    db_session.add(entry)
    await db_session.commit()

    actor = Actor(user_id=owner.id, role=Role.PATIENT)
    flags = await analytics_service.data_quality_flags(db_session, actor, patient.id)

    assert DataQualityFlag.FUTURE_DATED_ENTRY in flags
