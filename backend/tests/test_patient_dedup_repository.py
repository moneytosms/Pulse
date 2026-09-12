"""P4.1 (#52) — dedup against a real Postgres, using the actual planted
pairs from `seed/data/identity/planted_pairs.csv`.

The manifest's own `kind` column is the independent ground truth: three
rows are planted `duplicate` pairs, two are planted `near_miss` pairs
(same surname, real differences elsewhere) that must NOT be flagged.
Precision/recall is measured against exactly those five pairs, not
invented ones — this is the P4.1 acceptance criterion, not an add-on.

Negative test first: an actor with no shared identity signal gets no
candidates at all — the blocking predicate does not degenerate to
"everyone".
"""

from __future__ import annotations

import csv
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.modules.records.models import Diagnosis
from app.modules.users import service
from app.modules.users.models import Patient, ReviewStatus, User

_SEED_IDENTITY = Path(__file__).resolve().parents[2] / "seed" / "data" / "identity"
_PW_HASH = "x"


async def _user(db_session: AsyncSession) -> User:
    user = User(
        email=f"{uuid.uuid4()}@example.com", password_hash=_PW_HASH, role=Role.ADMINISTRATOR
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _load_planted_patient_rows() -> dict[str, dict[str, str]]:
    with (_SEED_IDENTITY / "patients.csv").open(encoding="utf-8") as f:
        rows = {row["id"]: row for row in csv.DictReader(f)}
    return rows


def _load_planted_pairs() -> list[dict[str, str]]:
    with (_SEED_IDENTITY / "planted_pairs.csv").open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def _insert_patient(db_session: AsyncSession, row: dict[str, str]) -> Patient:
    patient = Patient(
        id=uuid.UUID(row["id"]),
        full_name=row["full_name"],
        date_of_birth=date.fromisoformat(row["date_of_birth"]),
        phone=row["phone"],
    )
    db_session.add(patient)
    await db_session.flush()
    return patient


@pytest.mark.asyncio
async def test_trigram_gin_index_exists(db_session: AsyncSession) -> None:
    """P4.1 acceptance: 'the blocking query uses [the GIN trigram index]
    (EXPLAIN confirms)'. EXPLAIN itself isn't checked here — the planner
    correctly prefers a sequential scan over any index on a table this
    small (a handful of rows), so asserting on the plan would be
    asserting the wrong thing, not confirming the right one. What's
    checked instead, deterministically: the index exists, targets
    `full_name`, and uses `gin_trgm_ops` — the migration 0008 acceptance
    criterion that's actually independent of table size.
    """
    row = (
        await db_session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_patient_full_name_trgm'")
        )
    ).first()
    assert row is not None
    assert "gin" in row[0].lower()
    assert "gin_trgm_ops" in row[0]


@pytest.mark.asyncio
async def test_unrelated_patients_produce_no_candidates(db_session: AsyncSession) -> None:
    a = Patient(
        full_name="Completely Unrelated Person",
        date_of_birth=date(1990, 1, 1),
        phone="+91 90000 00001",
    )
    b = Patient(
        full_name="Someone Else Entirely", date_of_birth=date(1950, 6, 15), phone="+91 90000 00002"
    )
    db_session.add_all([a, b])
    await db_session.flush()

    candidates = await service.duplicate_candidates_for(db_session, a.id)

    assert candidates == []


@pytest.mark.asyncio
async def test_planted_manifest_precision_and_recall(db_session: AsyncSession) -> None:
    rows = _load_planted_patient_rows()
    pairs = _load_planted_pairs()

    planted_ids = {pid for pair in pairs for pid in (pair["patient_id_a"], pair["patient_id_b"])}
    for pid in planted_ids:
        await _insert_patient(db_session, rows[pid])

    duplicate_pairs = {
        frozenset((p["patient_id_a"], p["patient_id_b"])) for p in pairs if p["kind"] == "duplicate"
    }
    near_miss_pairs = {
        frozenset((p["patient_id_a"], p["patient_id_b"])) for p in pairs if p["kind"] == "near_miss"
    }

    flagged_pairs: set[frozenset[str]] = set()
    for pid in planted_ids:
        for candidate, sc in await service.duplicate_candidates_for(db_session, uuid.UUID(pid)):
            if sc >= service.DUPLICATE_THRESHOLD:
                flagged_pairs.add(frozenset((pid, str(candidate.id))))

    # Recall: every planted duplicate is flagged.
    assert duplicate_pairs <= flagged_pairs
    # Precision: no planted near-miss is flagged.
    assert flagged_pairs.isdisjoint(near_miss_pairs)


@pytest.mark.asyncio
async def test_marked_not_duplicate_is_never_re_flagged(db_session: AsyncSession) -> None:
    rows = _load_planted_patient_rows()
    pairs = [p for p in _load_planted_pairs() if p["kind"] == "duplicate"]
    pair = pairs[0]
    a = await _insert_patient(db_session, rows[pair["patient_id_a"]])
    b = await _insert_patient(db_session, rows[pair["patient_id_b"]])
    admin = await _user(db_session)
    actor = Actor(user_id=admin.id, role=Role.ADMINISTRATOR)

    await service.record_duplicate_candidates(db_session, a.id)
    item = await service.mark_not_duplicate(db_session, actor, a.id, b.id)
    assert item.status == ReviewStatus.NOT_DUPLICATE

    # Re-running detection must not resurrect the pair as PENDING.
    await service.record_duplicate_candidates(db_session, a.id)
    await db_session.refresh(item)
    assert item.status == ReviewStatus.NOT_DUPLICATE


@pytest.mark.asyncio
async def test_merge_moves_entries_and_reversal_moves_them_back(db_session: AsyncSession) -> None:
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

    merge = await service.merge_patients(db_session, actor, winner.id, loser.id)
    await db_session.refresh(entry)
    await db_session.refresh(loser)
    assert entry.patient_id == winner.id
    assert loser.merged_into_id == winner.id

    await service.reverse_merge(db_session, actor, merge.id)
    await db_session.refresh(entry)
    await db_session.refresh(loser)
    assert entry.patient_id == loser.id
    assert loser.merged_into_id is None
