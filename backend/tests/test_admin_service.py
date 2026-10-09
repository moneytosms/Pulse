"""P4.3 (#54) — admin module: duplicate review + human-only reversible merge.

Negative test first (backend.md, clinical-safety.md): an Administrator
actor hits every new admin function/route and gets no clinical data back,
ever (ADR-0007). The duplicate review queue returns identity fields and
entry counts only — never entry contents.

Written red: `app/modules/admin/{schemas,service,routes}.py` start empty.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.modules.records.models import Diagnosis
from app.modules.users import service as users_service
from app.modules.users.models import Patient, User

_PW_HASH = "x"


async def _user(db_session: AsyncSession, role: Role = Role.ADMINISTRATOR) -> User:
    user = User(
        email=f"{role.value.lower()}-{uuid.uuid4()}@example.com",
        password_hash=_PW_HASH,
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _patient(db_session: AsyncSession, **fields: object) -> Patient:
    patient = Patient(full_name="Test Patient", **fields)
    db_session.add(patient)
    await db_session.flush()
    return patient


async def test_non_administrator_cannot_read_duplicate_review_queue(
    db_session: AsyncSession,
) -> None:
    from app.modules.admin import service as admin_service

    staff = await _user(db_session, Role.PROVIDER_STAFF)
    actor = Actor(user_id=staff.id, role=Role.PROVIDER_STAFF)

    with pytest.raises(PulseError) as exc:
        await admin_service.duplicate_review_queue(db_session, actor)
    assert exc.value.code is ErrorCode.FORBIDDEN


async def test_duplicate_review_queue_returns_identity_and_counts_never_entry_content(
    db_session: AsyncSession,
) -> None:
    from app.modules.admin import service as admin_service

    a = Patient(full_name="Ramesh Menon", date_of_birth=date(1980, 1, 1), phone="+91 90000 00010")
    b = Patient(full_name="Menon Ramesh", date_of_birth=date(1980, 1, 1), phone="+91 90000 00010")
    db_session.add_all([a, b])
    await db_session.flush()

    entry = Diagnosis(
        patient_id=a.id,
        occurred_at=datetime(2020, 1, 1, tzinfo=UTC),
        code_system="SNOMED-CT",
        code="44054006",
        display_name="Type 2 diabetes mellitus",
    )
    db_session.add(entry)
    await db_session.commit()

    await users_service.record_duplicate_candidates(db_session, a.id)

    admin = await _user(db_session)
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)

    queue = await admin_service.duplicate_review_queue(db_session, actor)
    assert len(queue.items) == 1
    item = queue.items[0]

    # Identity + counts only.
    dumped = item.model_dump(by_alias=False)
    expected_keys = {"id", "full_name", "date_of_birth", "phone", "claimed", "entry_count"}
    for field in ("patient_a", "patient_b"):
        assert set(dumped[field].keys()) == expected_keys
    assert {item.patient_a.entry_count, item.patient_b.entry_count} == {1, 0}

    # No clinical content anywhere in the serialised payload — the
    # diagnosis's own display name must never surface here.
    assert "Type 2 diabetes mellitus" not in str(dumped)
    assert "44054006" not in str(dumped)


async def test_merge_and_reversal_require_administrator_actor(db_session: AsyncSession) -> None:
    from app.modules.admin import service as admin_service

    winner = Patient(full_name="Winner Patient", date_of_birth=date(1980, 1, 1))
    loser = Patient(full_name="Loser Patient", date_of_birth=date(1980, 1, 1))
    db_session.add_all([winner, loser])
    await db_session.flush()

    staff = await _user(db_session, Role.PROVIDER_STAFF)
    non_admin_actor = Actor(user_id=staff.id, role=Role.PROVIDER_STAFF)

    with pytest.raises(PulseError) as exc:
        await admin_service.merge(db_session, non_admin_actor, winner.id, loser.id)
    assert exc.value.code is ErrorCode.FORBIDDEN


async def test_merge_via_admin_service_moves_entries_and_reversal_moves_them_back(
    db_session: AsyncSession,
) -> None:
    from app.modules.admin import service as admin_service

    winner = Patient(full_name="Winner Patient", date_of_birth=date(1980, 1, 1))
    loser = Patient(full_name="Loser Patient", date_of_birth=date(1980, 1, 1))
    db_session.add_all([winner, loser])
    await db_session.flush()
    entry = Diagnosis(
        patient_id=loser.id,
        occurred_at=datetime(2020, 1, 1, tzinfo=UTC),
        code_system="SNOMED-CT",
        code="44054006",
        display_name="Type 2 diabetes mellitus",
    )
    db_session.add(entry)
    await db_session.flush()

    admin = await _user(db_session)
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)

    result = await admin_service.merge(db_session, actor, winner.id, loser.id)
    await db_session.refresh(entry)
    assert entry.patient_id == winner.id

    reversed_result = await admin_service.reverse(db_session, actor, result.id)
    await db_session.refresh(entry)
    assert entry.patient_id == loser.id
    assert reversed_result.reversed_at is not None
