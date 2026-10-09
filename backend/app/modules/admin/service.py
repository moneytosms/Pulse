"""Admin business rules (P4.3, #54).

No SQL, no FastAPI imports (backend.md). This module owns no tables of
its own — it composes `users.service` (duplicate review + merge/reversal,
P4.1/#52) and `records.service` (entry counts only, never content) through
their service interfaces, never their tables (backend.md, "modules
communicate through service interfaces").

Every function here is Administrator-only. The actual gate lives in the
functions being wrapped (`users.service._require_administrator`,
`records.service.entry_count_for_patient`) so there is exactly one place
each rule is enforced — this module never re-implements the check, it
just never calls anything that would let a non-Administrator through.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.pagination import Page
from app.modules.admin.schemas import (
    AdminPatientIdentity,
    DuplicateReviewCandidate,
    MergeRecord,
    MergeResult,
)
from app.modules.records import service as records_service
from app.modules.users import service as users_service


class _Patient(Protocol):
    id: UUID
    full_name: str
    date_of_birth: date | None
    phone: str | None
    user_id: UUID | None


class _Merge(Protocol):
    id: UUID
    winner_patient_id: UUID
    loser_patient_id: UUID
    occurred_at: datetime
    reversed_at: datetime | None


def _identity(patient: _Patient, count: int) -> AdminPatientIdentity:
    return AdminPatientIdentity(
        id=patient.id,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        phone=patient.phone,
        claimed=patient.user_id is not None,
        entry_count=count,
    )


async def duplicate_review_queue(
    session: AsyncSession, actor: Actor, *, cursor: str | None = None, limit: int = 50
) -> Page[DuplicateReviewCandidate]:
    """Identity fields + entry counts only, never entry content (ADR-0007,
    ADR-0011). `list_duplicate_review_queue` gates to Administrator."""
    items, next_cursor = await users_service.duplicate_review_page(
        session, actor, cursor=cursor, limit=limit
    )
    candidates: list[DuplicateReviewCandidate] = []
    patient_ids = list({pid for item in items for pid in (item.patient_id_a, item.patient_id_b)})
    patients = await users_service.patient_map(session, patient_ids)
    counts = await records_service.entry_counts_for_patients(session, actor, patient_ids)
    for item in items:
        patient_a = patients.get(item.patient_id_a)
        patient_b = patients.get(item.patient_id_b)
        if patient_a is None or patient_b is None:  # pragma: no cover - defensive
            continue
        candidates.append(
            DuplicateReviewCandidate(
                id=item.id,
                patient_a=_identity(patient_a, counts.get(patient_a.id, 0)),
                patient_b=_identity(patient_b, counts.get(patient_b.id, 0)),
                score=float(item.score),
                # `DuplicateReviewItem.status` maps to a plain `String`
                # column (not `SAEnum`), so the value read back off a real
                # row is already the raw string `ReviewStatus` value.
                status=str(item.status),
            )
        )
    return Page[DuplicateReviewCandidate](items=candidates, next_cursor=next_cursor)


async def mark_not_duplicate(
    session: AsyncSession, actor: Actor, patient_id_a: UUID, patient_id_b: UUID
) -> None:
    await users_service.mark_not_duplicate(session, actor, patient_id_a, patient_id_b)


def _to_merge_result(merge: _Merge) -> MergeResult:
    return MergeResult(
        id=merge.id,
        winner_patient_id=merge.winner_patient_id,
        loser_patient_id=merge.loser_patient_id,
        occurred_at=merge.occurred_at,
        reversed_at=merge.reversed_at,
    )


async def merge(
    session: AsyncSession, actor: Actor, winner_patient_id: UUID, loser_patient_id: UUID
) -> MergeResult:
    """Human-admin-only, reversible (ADR-0011). `merge_patients` gates to
    Administrator and rejects any other caller, including a background job."""
    result = await users_service.merge_patients(session, actor, winner_patient_id, loser_patient_id)
    return _to_merge_result(result)


async def reversible_merges(
    session: AsyncSession, actor: Actor, *, cursor: str | None = None, limit: int = 50
) -> Page[MergeRecord]:
    """`list_reversible_merges` gates to Administrator."""
    records: list[MergeRecord] = []
    merges, next_cursor = await users_service.reversible_merge_page(
        session, actor, cursor=cursor, limit=limit
    )
    patient_ids = list(
        {pid for merge in merges for pid in (merge.winner_patient_id, merge.loser_patient_id)}
    )
    patients = await users_service.patient_map(session, patient_ids)
    for merge in merges:
        winner = patients.get(merge.winner_patient_id)
        loser = patients.get(merge.loser_patient_id)
        if winner is None or loser is None:  # pragma: no cover - FK-guaranteed
            continue
        records.append(
            MergeRecord(
                **_to_merge_result(merge).model_dump(),
                winner_name=winner.full_name,
                loser_name=loser.full_name,
            )
        )
    return Page[MergeRecord](items=records, next_cursor=next_cursor)


async def reverse(session: AsyncSession, actor: Actor, merge_id: UUID) -> MergeResult:
    result = await users_service.reverse_merge(session, actor, merge_id)
    return _to_merge_result(result)
