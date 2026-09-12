"""#40, P3.4 — `access.resolve_patient_access`, branchy logic tested directly.

backend.md: "Unit tests are for genuinely branchy logic only" — this is
exactly that (permission resolution), so each Role branch gets its own
test against the resolution function itself, not just through an HTTP
round trip. Negative first: an actor with no relationship to the patient
resolves to no access, for every role including the ones that look
plausible at a glance (a Clinician with no live grant, an Administrator).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.modules.records import access
from app.modules.users.models import Patient, Provider, ProviderKind, ProviderStaff, User


async def _user(db_session: AsyncSession, role: Role) -> User:
    user = User(
        email=f"{role.value.lower()}-{uuid.uuid4()}@example.com",
        password_hash="x",
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


async def test_administrator_never_resolves_to_any_access(db_session: AsyncSession) -> None:
    """ADR-0007: an Administrator resolves to nothing, on every field —
    not a special case, just no branch ever setting one."""
    admin = await _user(db_session, Role.ADMINISTRATOR)
    patient = await _patient(db_session, None)
    await db_session.commit()
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.owns_own_history is False
    assert resolved.provider_id is None
    assert resolved.permissions == ()
    assert resolved.has_any_access is False


async def test_unrelated_patient_has_no_access_to_someone_elses_record(
    db_session: AsyncSession,
) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    stranger = await _user(db_session, Role.PATIENT)
    await db_session.commit()
    actor = Actor(user_id=stranger.id, role=Role.PATIENT)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.owns_own_history is False
    assert resolved.has_any_access is False


async def test_patient_owns_their_own_history(db_session: AsyncSession) -> None:
    owner = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, owner)
    await db_session.commit()
    actor = Actor(user_id=owner.id, role=Role.PATIENT)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.owns_own_history is True
    assert resolved.provider_id is None
    assert resolved.has_any_access is True


async def test_provider_staff_resolves_to_their_own_provider(db_session: AsyncSession) -> None:
    patient = await _patient(db_session, None)
    staff_user = await _user(db_session, Role.PROVIDER_STAFF)
    provider = Provider(name="Apollo", kind=ProviderKind.HOSPITAL, city="c", state="s")
    db_session.add(provider)
    await db_session.flush()
    db_session.add(ProviderStaff(user_id=staff_user.id, provider_id=provider.id))
    await db_session.commit()
    actor = Actor(user_id=staff_user.id, role=Role.PROVIDER_STAFF)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.owns_own_history is False
    assert resolved.provider_id == provider.id
    assert resolved.has_any_access is True


async def test_clinician_with_no_live_permission_has_no_access(db_session: AsyncSession) -> None:
    patient = await _patient(db_session, None)
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()
    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.permissions == ()
    assert resolved.has_any_access is False


async def test_clinician_with_a_live_permission_resolves_it(db_session: AsyncSession) -> None:
    """Written directly against `access_permission` (raw SQL, matching
    `live_permissions_for` — records does not import `consent.models`)
    so this test has no dependency on the still-empty `consent` service."""
    patient_user = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, patient_user)
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()

    consent_id = uuid.uuid4()
    permission_id = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=30)
    await db_session.execute(
        text(
            "INSERT INTO consent "
            "(id, patient_id, grantee_user_id, purpose, expires_at) "
            "VALUES (:id, :patient_id, :grantee_user_id, 'TREATMENT', :expires_at)"
        ),
        {
            "id": consent_id,
            "patient_id": patient.id,
            "grantee_user_id": clinician.id,
            "expires_at": expires_at,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO access_permission "
            "(id, consent_id, patient_id, grantee_user_id, entry_types, expires_at) "
            "VALUES (:id, :consent_id, :patient_id, :grantee_user_id, :entry_types, :expires_at)"
        ),
        {
            "id": permission_id,
            "consent_id": consent_id,
            "patient_id": patient.id,
            "grantee_user_id": clinician.id,
            "entry_types": ["LAB_REPORT"],
            "expires_at": expires_at,
        },
    )
    await db_session.commit()
    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert len(resolved.permissions) == 1
    assert resolved.permissions[0].id == permission_id
    assert resolved.permissions[0].entry_types == ["LAB_REPORT"]
    assert resolved.has_any_access is True


async def test_clinician_with_an_expired_permission_has_no_access(
    db_session: AsyncSession,
) -> None:
    """Not "live" — expired. Existence alone (row not deleted) must not
    be enough; the expiry has to be checked too."""
    patient_user = await _user(db_session, Role.PATIENT)
    patient = await _patient(db_session, patient_user)
    clinician = await _user(db_session, Role.CLINICIAN)
    await db_session.commit()

    consent_id = uuid.uuid4()
    expired_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.execute(
        text(
            "INSERT INTO consent "
            "(id, patient_id, grantee_user_id, purpose, expires_at) "
            "VALUES (:id, :patient_id, :grantee_user_id, 'TREATMENT', :expires_at)"
        ),
        {
            "id": consent_id,
            "patient_id": patient.id,
            "grantee_user_id": clinician.id,
            "expires_at": expired_at,
        },
    )
    await db_session.execute(
        text(
            "INSERT INTO access_permission "
            "(id, consent_id, patient_id, grantee_user_id, expires_at) "
            "VALUES (:id, :consent_id, :patient_id, :grantee_user_id, :expires_at)"
        ),
        {
            "id": uuid.uuid4(),
            "consent_id": consent_id,
            "patient_id": patient.id,
            "grantee_user_id": clinician.id,
            "expires_at": expired_at,
        },
    )
    await db_session.commit()
    actor = Actor(user_id=clinician.id, role=Role.CLINICIAN)

    resolved = await access.resolve_patient_access(db_session, actor, patient.id)

    assert resolved.permissions == ()
    assert resolved.has_any_access is False
