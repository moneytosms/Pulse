"""Identity business rules (G1 signatures).

No SQL, no FastAPI imports (backend.md). Other modules call these
functions; they never touch `users` tables or `users.repository`
directly. Mutations commit here — repository writes only flush.

Duplicate detection (P4.1, #52) lives here too, not in a separate
module: it operates entirely on Patient identity, which this module
already owns. Scoring is pure Python, no DB round trip — the candidate
set is already small after blocking (`repository.blocked_candidates`),
so re-scoring it in-process is simpler than a second SQL statement.
`pg_trgm` still does the expensive part: the blocking query's trigram-hit
predicate is a GIN index lookup; `score_pair` only needs to reproduce
trigram *similarity* (Jaccard over padded-trigram sets, matching
`pg_trgm`'s own definition) over the shortlisted pairs. Weights are
fixed by domain-model.md: name 0.5, DOB 0.3, phone 0.2.

`merge_patients`/`reverse_merge` import `records.service` inside the
function body, not at module level: `records.service` already imports
`users.service` (for actor-owns-patient resolution), and `audit.service`
imports both — a module-level import here would make that a real cycle
at interpreter start-up rather than a lazy one resolved by call time.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.transactions import transactional
from app.modules.patients.schemas import PatientProfile
from app.modules.users import repository
from app.modules.users.models import (
    DuplicateReviewItem,
    Patient,
    PatientMerge,
    Provider,
    ReviewStatus,
    User,
)


def _to_profile(patient: Patient) -> PatientProfile:
    return PatientProfile(
        id=patient.id,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        sex=patient.sex.value if patient.sex is not None else None,
        phone=patient.phone,
        address_line=patient.address_line,
        city=patient.city,
        state=patient.state,
        locale_preference=patient.locale_preference,
        claimed=patient.user_id is not None,
    )


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    return await repository.get_user_by_id(session, user_id)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return await repository.get_user_by_email(session, email)


async def get_patient(session: AsyncSession, patient_id: UUID) -> Patient | None:
    """One Patient by id. Other modules use this to check record ownership
    without importing the `users` tables."""
    return await repository.get_patient_by_id(session, patient_id)


async def get_provider_for_staff(session: AsyncSession, user_id: UUID) -> UUID | None:
    """The `provider_id` the given Provider Staff user acts for, or None."""
    staff = await repository.get_provider_staff_by_user_id(session, user_id)
    return staff.provider_id if staff is not None else None


async def get_provider(session: AsyncSession, provider_id: UUID) -> Provider | None:
    """One Provider organisation by id. Public identity only — no clinical
    data hangs off this."""
    return await repository.get_provider_by_id(session, provider_id)


async def register_identity(
    session: AsyncSession, *, email: str, password_hash: str, role: Role
) -> User:
    """Create the User and, for a PATIENT, a linked Patient row."""
    user = await repository.create_user(
        session, email=email, password_hash=password_hash, role=role
    )
    if role is Role.PATIENT:
        placeholder_name = email.split("@", 1)[0]
        await repository.create_patient(session, user_id=user.id, full_name=placeholder_name)
    await session.commit()
    return user


async def mark_verified(session: AsyncSession, user_id: UUID) -> None:
    await repository.mark_email_verified(session, user_id, datetime.now(UTC))
    await session.commit()


async def change_password(session: AsyncSession, user_id: UUID, new_password_hash: str) -> None:
    await repository.set_password_hash(session, user_id, new_password_hash)
    await session.commit()


async def get_own_patient_profile(session: AsyncSession, actor: Actor) -> PatientProfile | None:
    """The signed-in Patient's own profile. None if the actor owns no Patient."""
    patient = await repository.get_patient_by_user_id(session, actor.user_id)
    if patient is None:
        return None
    return _to_profile(patient)


async def get_patient_profile_for_actor(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> PatientProfile | None:
    """One Patient's identity profile, resolved through the same access
    rules as the clinical read.

    Identity fields only — no clinical content — but a bare `patient_id`
    is still a capability (`.claude/errors.md`, 2026-09-12), so *who* may
    resolve one is decided by `records.access.resolve_patient_access`, not
    by this docstring: the owner sees their row, Provider Staff see rows
    they filed against, a Clinician only with a live Consent or active
    break-glass, and an Administrator gets None (ADR-0007) — surfacing to
    the route as a 404, never a 403 (clinical-safety.md).

    `records.service` (not `records.access`) is imported lazily here —
    same pattern as `merge_patients` below: it already imports
    `users.service` at module level, so a module-level import of anything
    records-side risks a cycle at interpreter start-up. `access` itself is
    records-internal (the cross-module lint allows only `service`,
    `schemas` and `dependencies` to cross), so the resolution is reached
    through `records.service`'s own gate helper.
    """
    from app.modules.records import service as records_service

    resolved = await records_service.resolve_patient_access(session, actor, patient_id)
    if not resolved.has_any_access:
        return None
    patient = await repository.get_patient_by_id(session, patient_id)
    if patient is None:
        return None
    return _to_profile(patient)


async def set_locale_preference(session: AsyncSession, actor: Actor, locale: str) -> None:
    patient = await repository.get_patient_by_user_id(session, actor.user_id)
    if patient is None:
        return
    await repository.set_patient_locale(session, patient.id, locale)
    await session.commit()


# --- Duplicate detection (P4.1, #52) ---------------------------------------

NAME_WEIGHT = 0.5
DOB_WEIGHT = 0.3
PHONE_WEIGHT = 0.2

# Above this, a pair is worth a human's attention. Below it (the planted
# near-misses in seed/data/identity/planted_pairs.csv land at ~0.2), it
# never becomes a review item.
DUPLICATE_THRESHOLD = 0.5

_TOKEN_SPLIT = re.compile(r"[^\w]+", re.UNICODE)


def _require_administrator(actor: Actor) -> None:
    """Merge/reversal and review decisions are human-admin-only, never a
    background job (ADR-0011, #54). An `Actor` only ever exists after
    authentication (`AuthContext.actor`) — nothing in this codebase
    constructs one for a scheduled task — so gating on the role is
    sufficient to keep this off the detection pipeline's path, which
    calls `record_duplicate_candidates` with no actor at all."""
    if actor.role is not Role.ADMINISTRATOR:
        raise PulseError(
            ErrorCode.FORBIDDEN,
            "Only an Administrator may decide duplicate review items.",
            http_status=403,
        )


@dataclass(frozen=True)
class PatientIdentity:
    full_name: str
    date_of_birth: date | None
    phone: str | None


def _normalise_name(name: str) -> str:
    """Lowercase, strip punctuation, sort tokens.

    Indian naming order varies by region ("Menon Ramesh" vs "Ramesh
    Menon" are the same person), so tokens are sorted before comparison
    rather than compared positionally (database.md).
    """
    tokens = [t for t in _TOKEN_SPLIT.split(name.lower()) if t]
    return " ".join(sorted(tokens))


def _trigrams(s: str) -> set[str]:
    # pg_trgm pads with two leading/trailing spaces before splitting into
    # 3-grams; reproduced here so the two are comparable.
    padded = f"  {s}  "
    return {padded[i : i + 3] for i in range(len(padded) - 2)}


def _name_similarity(a: str, b: str) -> float:
    ta, tb = _trigrams(_normalise_name(a)), _trigrams(_normalise_name(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dob_similarity(a: date | None, b: date | None) -> float:
    """1.0 exact; high but <1 for a same-year typo of a few days
    (transposition tolerance); decays to 0 within a year so a
    year-apart sibling does not read as a DOB match.
    """
    if a is None or b is None:
        return 0.0
    diff_days = abs((a - b).days)
    if diff_days == 0:
        return 1.0
    if diff_days <= 3:
        return 0.85
    if diff_days <= 10:
        return 0.5
    return max(0.0, 1 - diff_days / 365)


def _phone_similarity(a: str | None, b: str | None) -> float:
    return 1.0 if a and b and a == b else 0.0


def score_pair(a: PatientIdentity, b: PatientIdentity) -> float:
    name_sim = _name_similarity(a.full_name, b.full_name)
    dob_sim = _dob_similarity(a.date_of_birth, b.date_of_birth)
    phone_sim = _phone_similarity(a.phone, b.phone)
    return NAME_WEIGHT * name_sim + DOB_WEIGHT * dob_sim + PHONE_WEIGHT * phone_sim


def _identity_of(patient: Patient) -> PatientIdentity:
    return PatientIdentity(
        full_name=patient.full_name, date_of_birth=patient.date_of_birth, phone=patient.phone
    )


async def duplicate_candidates_for(
    session: AsyncSession, patient_id: UUID
) -> list[tuple[Patient, float]]:
    """Blocking then scoring: the composable pipeline behind review-item
    creation. Returns every blocked candidate paired with its score, not
    just the ones over threshold, so a caller can inspect near-misses too.
    """
    subject = await repository.get_patient_by_id(session, patient_id)
    if subject is None:
        return []
    subject_identity = _identity_of(subject)

    candidates = await repository.blocked_candidates(session, subject)
    return [(c, score_pair(subject_identity, _identity_of(c))) for c in candidates]


async def record_duplicate_candidates(
    session: AsyncSession, patient_id: UUID
) -> list[DuplicateReviewItem]:
    """Creates/updates `duplicate_review_item` rows for every candidate
    scoring at or above `DUPLICATE_THRESHOLD`. A pair already marked
    `NOT_DUPLICATE` is left alone — never re-flagged (ADR-0011).
    """
    scored = await duplicate_candidates_for(session, patient_id)
    items: list[DuplicateReviewItem] = []
    for candidate, score in scored:
        if score < DUPLICATE_THRESHOLD:
            continue
        item = await repository.upsert_review_item(
            session,
            patient_id_a=patient_id,
            patient_id_b=candidate.id,
            score=Decimal(str(round(score, 3))),
        )
        if item is not None:
            items.append(item)
    await session.commit()
    return items


async def list_duplicate_review_queue(
    session: AsyncSession, actor: Actor
) -> list[DuplicateReviewItem]:
    """`PENDING` review items only — decided pairs are never re-flagged
    (ADR-0011). Human-admin-only, same gate as merge/reversal."""
    _require_administrator(actor)
    return await repository.list_pending_review_items(session)


async def mark_not_duplicate(
    session: AsyncSession, actor: Actor, patient_id_a: UUID, patient_id_b: UUID
) -> DuplicateReviewItem:
    _require_administrator(actor)
    item = await repository.set_review_status(
        session,
        patient_id_a=patient_id_a,
        patient_id_b=patient_id_b,
        status=ReviewStatus.NOT_DUPLICATE,
        decided_by_user_id=actor.user_id,
    )
    await session.commit()
    return item


@transactional
async def merge_patients(
    session: AsyncSession, actor: Actor, winner_id: UUID, loser_id: UUID
) -> PatientMerge:
    """Human-only, reversible (ADR-0011). Reassigns every Medical Entry
    from the loser to the winner and tombstones the loser with
    `merged_into_id` — never deletes it, so audit events referencing the
    loser stay resolvable.
    """
    from app.modules.records import service as records_service

    _require_administrator(actor)
    if winner_id == loser_id:
        raise PulseError(ErrorCode.CONFLICT, "Cannot merge a patient into itself.", http_status=409)

    locked = {p.id: p for p in await repository.lock_patients(session, [winner_id, loser_id])}
    winner = locked.get(winner_id)
    loser = locked.get(loser_id)
    if winner is None or loser is None:
        raise PulseError(ErrorCode.NOT_FOUND, "Both patients must exist.", http_status=404)

    if (
        winner.merged_into_id is not None
        or loser.merged_into_id is not None
        or loser.user_id is not None
        or await repository.has_open_merge(session, [winner_id, loser_id])
    ):
        raise PulseError(
            ErrorCode.CONFLICT,
            "Merge ownership or history conflicts; the losing patient must be unclaimed.",
            http_status=409,
        )
    from app.modules.consent import service as consent_service

    if await consent_service.has_live_patient_grants(session, loser_id):
        raise PulseError(
            ErrorCode.CONFLICT,
            "Losing identity has live grants; resolve them before merging.",
            http_status=409,
        )
    moved_ids = await records_service.reassign_patient_entries(
        session, actor, from_patient_id=loser_id, to_patient_id=winner_id
    )
    loser.merged_into_id = winner_id

    merge = PatientMerge(
        id=uuid.uuid4(),
        winner_patient_id=winner_id,
        loser_patient_id=loser_id,
        actor_user_id=actor.user_id,
        moved_entry_ids=[str(i) for i in moved_ids],
        occurred_at=await repository.operation_time(session),
    )
    session.add(merge)

    await repository.set_review_status(
        session,
        patient_id_a=winner_id,
        patient_id_b=loser_id,
        status=ReviewStatus.MERGED,
        decided_by_user_id=actor.user_id,
    )
    from app.modules.audit import service as audit_service

    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.PATIENT_MERGED,
        resource_type="patient_merge",
        resource_id=merge.id,
        patient_id=winner_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return merge


async def list_reversible_merges(session: AsyncSession, actor: Actor) -> list[PatientMerge]:
    """Unreversed merges, newest first, so a reversal does not depend on
    the merge id from the session that performed it (ADR-0011).
    Human-admin-only, same gate as merge/reversal."""
    _require_administrator(actor)
    return await repository.list_unreversed_merges(session)


@transactional
async def reverse_merge(session: AsyncSession, actor: Actor, merge_id: UUID) -> PatientMerge:
    """Reverse only when ownership and later clinical dependencies are safe."""
    from app.modules.records import service as records_service

    _require_administrator(actor)
    merge = await repository.get_merge_for_update(session, merge_id)
    if merge is None:
        raise PulseError(ErrorCode.NOT_FOUND, "Merge not found.", http_status=404)
    if merge.reversed_at is not None:
        raise PulseError(ErrorCode.CONFLICT, "Merge already reversed.", http_status=409)

    locked = {
        p.id: p
        for p in await repository.lock_patients(
            session, [merge.winner_patient_id, merge.loser_patient_id]
        )
    }
    loser = locked[merge.loser_patient_id]
    if loser.merged_into_id != merge.winner_patient_id or await repository.has_open_merge(
        session, list(locked), excluding=merge.id
    ):
        raise PulseError(ErrorCode.CONFLICT, "Merge history changed.", http_status=409)
    entry_ids = [UUID(i) for i in merge.moved_entry_ids]
    if await records_service.entry_reassignment_conflicts(
        session, actor, entry_ids, merge.winner_patient_id, merge.occurred_at
    ):
        raise PulseError(
            ErrorCode.CONFLICT,
            "Moved entries have changed; reversal needs manual review.",
            http_status=409,
        )
    await records_service.reverse_entry_reassignment(
        session, actor, entry_ids=entry_ids, to_patient_id=merge.loser_patient_id
    )

    loser.merged_into_id = None

    merge.reversed_at = datetime.now(UTC)
    from app.modules.audit import service as audit_service

    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.MERGE_REVERSED,
        resource_type="patient_merge",
        resource_id=merge.id,
        patient_id=merge.winner_patient_id,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    return merge


async def lock_patient_for_write(session: AsyncSession, patient_id: UUID) -> None:
    patients = await repository.lock_patients(session, [patient_id])
    if not patients:
        raise PulseError(ErrorCode.NOT_FOUND, "Patient not found.", http_status=404)
    if patients[0].merged_into_id is not None:
        raise PulseError(
            ErrorCode.CONFLICT, "Patient was merged; use the surviving identity.", http_status=409
        )


async def duplicate_review_page(
    session: AsyncSession, actor: Actor, *, cursor: str | None, limit: int
) -> tuple[list[DuplicateReviewItem], str | None]:
    _require_administrator(actor)
    return await repository.pending_review_page(session, cursor=cursor, limit=limit)


async def reversible_merge_page(
    session: AsyncSession, actor: Actor, *, cursor: str | None, limit: int
) -> tuple[list[PatientMerge], str | None]:
    _require_administrator(actor)
    return await repository.unreversed_merge_page(session, cursor=cursor, limit=limit)


def audit_patient_scope(
    patient_id: UUID, event_patient_id: ColumnElement[UUID | None]
) -> ColumnElement[bool]:
    """Audit history follows current tombstones without rewriting historical rows."""
    return repository.audit_patient_scope(patient_id, event_patient_id)


async def patient_map(session: AsyncSession, patient_ids: list[UUID]) -> dict[UUID, Patient]:
    return await repository.patient_map(session, patient_ids)


async def user_email_map(session: AsyncSession, user_ids: list[UUID]) -> dict[UUID, str]:
    return await repository.user_email_map(session, user_ids)
