"""#39/#41, P3.3+P3.5 — `accessible_entries` composes the real read rules
(ADR-0006).

Repository-level, no HTTP, no service layer: exercises the query builder
directly against a real Postgres. Negative first (backend.md, "write the
negative test first") — an actor unrelated to the patient must get an
EMPTY result set. A positive-only suite would pass just as happily if
`accessible_entries` still returned everything.

Rules 3-4 (this is the choke point, #41 — deliberately not split across
parallel agents): a Clinician with live Consent (entry-type + date
scoped), and break-glass (time-boxed, unscoped). Revocation deletes the
`access_permission` row (clinical-safety.md), so "revoked" and "no
permission at all" are the same case here; "expired" is tested
separately since the row still exists, just past `expires_at`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import records_helpers as rh
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.modules.consent.models import AccessPermission, BreakGlassAccess, Consent
from app.modules.consent.schemas import ConsentPurpose
from app.modules.records import repository
from app.modules.users.models import Patient, Provider, ProviderKind, ProviderStaff, User

_PW_HASH = "x"  # never authenticated through; password_hash is NOT NULL only


async def _user(db_session: AsyncSession, role: Role) -> User:
    user = User(
        email=f"{role.value.lower()}-{uuid.uuid4()}@example.com",
        password_hash=_PW_HASH,
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _patient(db_session: AsyncSession, user: User | None) -> Patient:
    patient = Patient(user_id=user.id if user else None, full_name="Test Patient")
    db_session.add(patient)
    await db_session.flush()
    return patient


async def _provider(db_session: AsyncSession, name: str = "Test Provider") -> Provider:
    provider = Provider(name=name, kind=ProviderKind.HOSPITAL, city="Chennai", state="Tamil Nadu")
    db_session.add(provider)
    await db_session.flush()
    return provider


async def _staff(db_session: AsyncSession, user: User, provider: Provider) -> ProviderStaff:
    staff = ProviderStaff(user_id=user.id, provider_id=provider.id)
    db_session.add(staff)
    await db_session.flush()
    return staff


async def _live_permission(
    db_session: AsyncSession,
    *,
    patient: Patient,
    clinician: User,
    entry_types: list[str] | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    expires_at: datetime,
) -> AccessPermission:
    """A live `access_permission` row, with the `consent` row it is
    derived from (the FK is mandatory — ADR-0010, break-glass is the one
    access path that does *not* go through Consent)."""
    consent = Consent(
        patient_id=patient.id,
        grantee_user_id=clinician.id,
        entry_types=entry_types,
        from_date=from_date,
        to_date=to_date,
        purpose=ConsentPurpose.TREATMENT,
        expires_at=expires_at,
    )
    db_session.add(consent)
    await db_session.flush()
    permission = AccessPermission(
        consent_id=consent.id,
        patient_id=patient.id,
        grantee_user_id=clinician.id,
        entry_types=entry_types,
        from_date=from_date,
        to_date=to_date,
        expires_at=expires_at,
    )
    db_session.add(permission)
    await db_session.flush()
    return permission


async def _break_glass(
    db_session: AsyncSession, *, patient: Patient, clinician: User, expires_at: datetime
) -> BreakGlassAccess:
    grant = BreakGlassAccess(
        patient_id=patient.id,
        clinician_user_id=clinician.id,
        justification="Patient unresponsive in ED, no consent on file.",
        expires_at=expires_at,
    )
    db_session.add(grant)
    await db_session.flush()
    return grant


async def test_unrelated_actor_sees_no_entries(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Wrong patient, wrong provider: `accessible_entries` returns nothing."""
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )

    stranger = await _user(db_session, Role.PATIENT)
    await db_session.commit()
    actor = Actor(user_id=stranger.id, role=Role.PATIENT)

    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_administrator_sees_no_entries_even_for_their_own_record(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """ADR-0007: no rule ever matches an Administrator — not even one
    whose `user_id` happens to also be a Patient's owner (the mapping is
    never actually made this way, but the rule must hold structurally)."""
    admin = await _user(db_session, Role.ADMINISTRATOR)
    patient = await _patient(db_session, admin)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)

    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_patient_sees_their_own_entry(
    db_session: AsyncSession, app_database_url: str
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    await db_session.commit()
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    actor = Actor(user_id=owner.id, role=Role.PATIENT)

    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert {r.id for r in rows} == {entry_id}


async def test_provider_staff_sees_only_their_own_providers_entries(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Rule 2 narrows to the *authoring* Provider — not every entry."""
    patient_user = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, patient_user)
    staff_user = await _user(db_session, Role.PROVIDER_STAFF)
    own_provider = await _provider(db_session, "Own Provider")
    other_provider = await _provider(db_session, "Other Provider")
    await _staff(db_session, staff_user, own_provider)
    await db_session.commit()

    own_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        source_provider_id=own_provider.id,
    )
    other_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
        source_provider_id=other_provider.id,
    )

    actor = Actor(user_id=staff_user.id, role=Role.PROVIDER_STAFF)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    ids = {r.id for r in rows}
    assert ids == {own_entry}
    assert other_entry not in ids


async def test_provider_staff_at_a_different_provider_sees_nothing(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Same shape as the unrelated-actor case, but for the Provider Staff
    branch specifically: staff at Provider B querying a patient with only
    Provider A's entries gets an empty set, not an error."""
    patient_user = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, patient_user)
    provider_a = await _provider(db_session, "Provider A")
    provider_b = await _provider(db_session, "Provider B")
    staff_b_user = await _user(db_session, Role.PROVIDER_STAFF)
    await _staff(db_session, staff_b_user, provider_b)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        source_provider_id=provider_a.id,
    )

    actor = Actor(user_id=staff_b_user.id, role=Role.PROVIDER_STAFF)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_clinician_with_no_permission_or_break_glass_sees_nothing(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Rule 3/4's negative case: a Clinician who holds neither a live
    `access_permission` row nor an active break-glass grant is exactly
    the unrelated-actor case."""
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_clinician_with_expired_permission_sees_nothing(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """The row still exists (unlike revocation, which deletes it) — but
    `expires_at` is in the past, so it must not grant access."""
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await _live_permission(
        db_session,
        patient=patient,
        clinician=clinician,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_clinician_with_live_unscoped_permission_sees_all_entries(
    db_session: AsyncSession, app_database_url: str
) -> None:
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await _live_permission(
        db_session,
        patient=patient,
        clinician=clinician,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert {r.id for r in rows} == {entry_id}


async def test_lab_scoped_consent_does_not_leak_a_clinical_note(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Consent scoped to one entry type must not leak other types — named
    explicitly in #47's adversarial-suite acceptance criteria."""
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    lab_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
    )
    note_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
        entry_type="CLINICAL_NOTE",
    )
    await _live_permission(
        db_session,
        patient=patient,
        clinician=clinician,
        entry_types=["LAB_REPORT"],
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    ids = {r.id for r in (await db_session.execute(stmt)).scalars().all()}
    assert ids == {lab_entry}
    assert note_entry not in ids


async def test_date_scoped_consent_excludes_entries_outside_the_window(
    db_session: AsyncSession, app_database_url: str
) -> None:
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    in_window = await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2024, 6, 15, tzinfo=UTC)
    )
    before_window = await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2024, 1, 1, tzinfo=UTC)
    )
    after_window = await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2024, 12, 31, tzinfo=UTC)
    )
    await _live_permission(
        db_session,
        patient=patient,
        clinician=clinician,
        from_date=date(2024, 6, 1),
        to_date=date(2024, 6, 30),
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    ids = {r.id for r in (await db_session.execute(stmt)).scalars().all()}
    assert ids == {in_window}
    assert before_window not in ids
    assert after_window not in ids


async def test_expired_break_glass_sees_nothing(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """The break-glass window is exactly the granted duration, not
    open-ended — one minute past `expires_at` and access is gone."""
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    await rh.insert_entry(
        app_database_url, patient_id=patient.id, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )
    await _break_glass(
        db_session,
        patient=patient,
        clinician=clinician,
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    rows = (await db_session.execute(stmt)).scalars().all()
    assert rows == []


async def test_active_break_glass_sees_all_entries_unscoped(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """Break-glass is emergency access without Consent (domain-model.md)
    — unlike rule 3, it carries no entry-type or date scoping."""
    patient = await _patient(db_session, await _user(db_session, Role.PATIENT))
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    lab_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
    )
    note_entry = await rh.insert_entry(
        app_database_url,
        patient_id=patient.id,
        occurred_at=datetime(2025, 1, 2, tzinfo=UTC),
        entry_type="CLINICAL_NOTE",
    )
    await _break_glass(
        db_session,
        patient=patient,
        clinician=clinician,
        expires_at=datetime.now(UTC) + timedelta(minutes=60),
    )
    await db_session.commit()

    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)
    stmt = await repository.accessible_entries(db_session, actor, patient.id)
    ids = {r.id for r in (await db_session.execute(stmt)).scalars().all()}
    assert ids == {lab_entry, note_entry}
