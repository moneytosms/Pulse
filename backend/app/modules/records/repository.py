"""Records repository — all SQL for Medical Entries and Documents.

`accessible_entries` (ADR-0006) is the one query builder every clinical
read composes from, all four rules: the Patient's own history (#39), a
Provider Staff member's own Provider (#39), a Clinician with live,
entry-type/date-scoped Consent (#41), and break-glass — unscoped, exactly
the granted 60-minute window (#41). Every entry-returning function takes
an `actor`: if a signature has no actor, the access rules have nowhere to
apply (clinical-safety.md).

An actor matching no rule (wrong patient, wrong provider, or an
Administrator — ADR-0007) gets an empty result set here, never a raised
error: `accessible_entries` is a filter, not a permission check with a
side exit. Nothing special-cases Administrator; no rule below ever
matches that role, so the `or_()` is simply empty for it.

`list_timeline` / `get_entry` land here in P2.3 / P2.5; `insert_entry` in
P2.5; `supersede_entry` in P2.7; the document functions in P2.6.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, Select, and_, false, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectin_polymorphic

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.records.models import (
    ClinicalNote,
    Diagnosis,
    EntryType,
    LabReport,
    MedicalDocument,
    MedicalEntry,
    Prescription,
    Procedure,
)
from app.modules.records.schemas import DocumentCreate, EntryCreate
from app.modules.users import service as users_service

_SUBTYPES = (Diagnosis, Prescription, LabReport, Procedure, ClinicalNote)
_MAX_LIMIT = 100


@dataclass(frozen=True)
class LivePermission:
    """One live `access_permission` row granting `grantee_user_id` (a
    Clinician) access to a Patient — rule 3 material for #41 (P3.5).

    Column names mirror `consent/models.py::AccessPermission`; read there
    for reference. This is raw SQL rather than the ORM entity: `records`
    does not import `consent.models` (backend.md — modules communicate
    through `service`, never another module's tables), and
    `consent.service` is still a P3.2 stub with nothing to call.
    """

    id: UUID
    entry_types: list[str] | None
    from_date: date | None
    to_date: date | None
    expires_at: datetime


async def live_permissions_for(
    session: AsyncSession, *, patient_id: UUID, grantee_user_id: UUID
) -> list[LivePermission]:
    """LIVE `access_permission` rows for one (patient, grantee) pair —
    not expired. Revocation deletes the row transactionally
    (clinical-safety.md), so existence already means "not revoked"; the
    `expires_at` check is the rest of "live"."""
    stmt = text(
        "SELECT id, entry_types, from_date, to_date, expires_at "
        "FROM access_permission "
        "WHERE patient_id = :patient_id "
        "AND grantee_user_id = :grantee_user_id "
        "AND expires_at > now()"
    )
    rows = (
        await session.execute(
            stmt, {"patient_id": patient_id, "grantee_user_id": grantee_user_id}
        )
    ).mappings().all()
    return [
        LivePermission(
            id=row["id"],
            entry_types=row["entry_types"],
            from_date=row["from_date"],
            to_date=row["to_date"],
            expires_at=row["expires_at"],
        )
        for row in rows
    ]


async def actor_owns_patient(session: AsyncSession, actor: Actor, patient_id: UUID) -> bool:
    """Rule 1: `actor` is the Patient identified by `patient_id`."""
    if actor.role is not Role.PATIENT:
        return False
    patient = await users_service.get_patient(session, patient_id)
    return patient is not None and patient.user_id == actor.user_id


async def provider_id_for_staff_actor(session: AsyncSession, actor: Actor) -> UUID | None:
    """Rule 2's Provider: the one `actor` (a Provider Staff member) works
    for, or None if `actor` is not staff, or staff at no Provider."""
    if actor.role is not Role.PROVIDER_STAFF:
        return None
    return await users_service.get_provider_for_staff(session, actor.user_id)


async def active_break_glass_for(
    session: AsyncSession, *, patient_id: UUID, clinician_user_id: UUID
) -> bool:
    """Rule 4: an unexpired break-glass grant for this (patient, Clinician)
    pair. Exactly the granted window — no revoke, only expiry
    (clinical-safety.md, "not open-ended"). Raw SQL for the same reason as
    `live_permissions_for`: `records` does not import `consent.models`."""
    stmt = text(
        "SELECT 1 FROM break_glass_access "
        "WHERE patient_id = :patient_id "
        "AND clinician_user_id = :clinician_user_id "
        "AND expires_at > now() LIMIT 1"
    )
    row = (
        await session.execute(
            stmt, {"patient_id": patient_id, "clinician_user_id": clinician_user_id}
        )
    ).first()
    return row is not None


def _permission_condition(permission: LivePermission, patient_id: UUID) -> Any:
    """Rule 3's `and_()` branch for one live `access_permission` row:
    scoped to the patient, and — when set — to its entry types and date
    window. `entry_types` / dates of `None` mean unscoped on that axis."""
    parts: list[Any] = [MedicalEntry.patient_id == patient_id]
    if permission.entry_types is not None:
        parts.append(MedicalEntry.entry_type.in_(permission.entry_types))
    if permission.from_date is not None:
        parts.append(
            MedicalEntry.occurred_at
            >= datetime.combine(permission.from_date, time.min, tzinfo=UTC)
        )
    if permission.to_date is not None:
        parts.append(
            MedicalEntry.occurred_at
            <= datetime.combine(permission.to_date, time.max, tzinfo=UTC)
        )
    return and_(*parts)


async def accessible_entries(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> Select[Any]:
    """The subset of a Patient's Medical Entries `actor` may read.

    Composable filter, not a result set — each rule below is an `or_()`
    branch.
    """
    conditions: list[Any] = []

    if await actor_owns_patient(session, actor, patient_id):
        conditions.append(MedicalEntry.patient_id == patient_id)

    provider_id = await provider_id_for_staff_actor(session, actor)
    if provider_id is not None:
        conditions.append(
            and_(
                MedicalEntry.patient_id == patient_id,
                MedicalEntry.source_provider_id == provider_id,
            )
        )

    if actor.role is Role.CLINICIAN:
        for permission in await live_permissions_for(
            session, patient_id=patient_id, grantee_user_id=actor.user_id
        ):
            conditions.append(_permission_condition(permission, patient_id))

        if await active_break_glass_for(
            session, patient_id=patient_id, clinician_user_id=actor.user_id
        ):
            conditions.append(MedicalEntry.patient_id == patient_id)

    if not conditions:
        conditions.append(false())

    return select(MedicalEntry).where(or_(*conditions))


def _pack_cursor(occurred_at: datetime, entry_id: UUID) -> str:
    return encode_cursor(f"{occurred_at.isoformat()}|{entry_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    raw = decode_cursor(cursor)
    ts, sep, uid = raw.partition("|")
    try:
        if not sep:
            raise ValueError("missing separator")
        return datetime.fromisoformat(ts), UUID(uid)
    except ValueError as exc:
        raise PulseError(ErrorCode.VALIDATION_ERROR, "Invalid cursor.") from exc


async def list_timeline(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    entry_type: EntryType | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[MedicalEntry], str | None]:
    """`occurred_at DESC`, `superseded_by_id IS NULL`, polymorphic via
    `selectin_polymorphic` (also the async `MissingGreenlet` fix). Opaque
    keyset cursor over `(occurred_at, id)` — never offset."""
    limit = max(1, min(limit, _MAX_LIMIT))
    stmt = (await accessible_entries(session, actor, patient_id)).where(
        MedicalEntry.superseded_by_id.is_(None)
    )
    if entry_type is not None:
        stmt = stmt.where(MedicalEntry.entry_type == entry_type)
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        stmt = stmt.where(
            or_(
                MedicalEntry.occurred_at < c_at,
                (MedicalEntry.occurred_at == c_at) & (MedicalEntry.id < c_id),
            )
        )
    stmt = (
        stmt.order_by(MedicalEntry.occurred_at.desc(), MedicalEntry.id.desc())
        .options(selectin_polymorphic(MedicalEntry, list(_SUBTYPES)))
        .limit(limit + 1)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.occurred_at, tail.id)
    return rows, next_cursor


async def get_entry(
    session: AsyncSession, actor: Actor, entry_id: UUID
) -> MedicalEntry | None:
    """One entry by id, subtype loaded, reachable even when superseded,
    gated by `accessible_entries` — the same rules the timeline applies.

    `accessible_entries` takes a `patient_id`, which isn't known ahead of
    an id lookup, so this is two queries: a minimal one to find it, then
    the real gated fetch. Either an inaccessible entry or one with no
    matching id at all returns None — the caller can't tell them apart,
    which is the point (clinical-safety.md: 404, never 403).
    """
    patient_id = await session.scalar(
        select(MedicalEntry.patient_id).where(MedicalEntry.id == entry_id)
    )
    if patient_id is None:
        return None
    stmt = (
        (await accessible_entries(session, actor, patient_id))
        .where(MedicalEntry.id == entry_id)
        .options(selectin_polymorphic(MedicalEntry, list(_SUBTYPES)))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_entry_unfiltered(
    session: AsyncSession, actor: Actor, entry_id: UUID
) -> MedicalEntry | None:
    """Raw fetch by id — no `accessible_entries` gating. Only the read
    paths (`get_entry`, `add_document`, `get_document`, `list_timeline`)
    narrow via `accessible_entries` (#39); the coarse Phase 2 Provider
    Staff write allowance (`insert_entry`'s post-write fetch,
    `supersede_entry`'s lookup of the original) still applies here, on
    purpose. `actor` stays a required parameter (clinical-safety.md) even
    though this function does not use it to filter — the name says why.
    """
    stmt = (
        select(MedicalEntry)
        .where(MedicalEntry.id == entry_id)
        .options(selectin_polymorphic(MedicalEntry, list(_SUBTYPES)))
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_superseding_original_id(
    session: AsyncSession, entry_id: UUID
) -> UUID | None:
    """The id of the Entry that `entry_id` supersedes, if any (reverse of
    `superseded_by_id`). Non-clinical, no actor needed."""
    stmt = select(MedicalEntry.id).where(MedicalEntry.superseded_by_id == entry_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_documents(
    session: AsyncSession, entry_id: UUID
) -> list[MedicalDocument]:
    """Document metadata for one Entry. Access is gated on the Entry by the
    caller; this is a plain child fetch."""
    stmt = select(MedicalDocument).where(MedicalDocument.entry_id == entry_id)
    return list((await session.execute(stmt)).scalars().all())


def _subtype_kwargs(entry_type: EntryType, payload: EntryCreate) -> dict[str, Any]:
    if entry_type in (EntryType.DIAGNOSIS, EntryType.PROCEDURE):
        return {
            "code_system": payload.code_system,
            "code": payload.code,
            "display_name": payload.display_name,
        }
    if entry_type is EntryType.LAB_REPORT:
        return {
            "code_system": payload.code_system,
            "code": payload.code,
            "display_name": payload.display_name,
            "value_numeric": payload.value_numeric,
            "value_text": payload.value_text,
            "unit": payload.unit,
            "reference_low": payload.reference_low,
            "reference_high": payload.reference_high,
        }
    if entry_type is EntryType.PRESCRIPTION:
        return {
            "medication_name": payload.medication_name,
            "code_system": payload.code_system,
            "code": payload.code,
            "display_name": payload.display_name,
            "dosage": payload.dosage,
            "frequency": payload.frequency,
            "route": payload.route,
        }
    return {"text": payload.text}


_SUBTYPE_CLASS: dict[EntryType, type[MedicalEntry]] = {
    EntryType.DIAGNOSIS: Diagnosis,
    EntryType.PROCEDURE: Procedure,
    EntryType.LAB_REPORT: LabReport,
    EntryType.PRESCRIPTION: Prescription,
    EntryType.CLINICAL_NOTE: ClinicalNote,
}


async def insert_entry(
    session: AsyncSession, actor: Actor, patient_id: UUID, payload: EntryCreate
) -> MedicalEntry:
    """Insert a trunk row plus its subtype row in one flush. Never updates
    in place. `author_user_id` is the acting user."""
    cls = _SUBTYPE_CLASS[payload.entry_type]
    entry = cls(
        patient_id=patient_id,
        entry_type=payload.entry_type,
        occurred_at=payload.occurred_at,
        is_critical=payload.is_critical,
        source_provider_id=payload.source_provider_id,
        author_user_id=actor.user_id,
        entry_metadata={},  # provenance only, set by the import pipeline — never the wire
        **_subtype_kwargs(payload.entry_type, payload),
    )
    session.add(entry)
    await session.flush()
    return entry


async def supersede_entry(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    original_id: UUID,
    replacement_payload: EntryCreate,
) -> MedicalEntry | None:
    """Insert the replacement, then the one permitted UPDATE on a clinical
    row — `superseded_by_id` on the original, and only when it is still
    NULL. Returns None when zero rows matched (already superseded); the
    caller rolls the replacement insert back and answers 409."""
    replacement = await insert_entry(session, actor, patient_id, replacement_payload)
    result = await session.execute(
        update(MedicalEntry)
        .where(
            (MedicalEntry.id == original_id)
            & MedicalEntry.superseded_by_id.is_(None)
        )
        .values(superseded_by_id=replacement.id)
        .execution_options(synchronize_session=False)
    )
    if not isinstance(result, CursorResult) or result.rowcount == 0:
        return None
    return replacement


async def add_document(
    session: AsyncSession, actor: Actor, entry_id: UUID, meta: DocumentCreate
) -> MedicalDocument:
    """Record metadata for a file already stored behind the
    StorageProvider. The bytes and checksum are the service's concern."""
    doc = MedicalDocument(
        entry_id=entry_id,
        filename=meta.filename,
        mime_type=meta.mime_type,
        size_bytes=meta.size_bytes,
        storage_path=meta.storage_path,
        checksum_sha256=meta.checksum_sha256,
    )
    session.add(doc)
    await session.flush()
    return doc


async def get_document(
    session: AsyncSession, actor: Actor, document_id: UUID
) -> MedicalDocument | None:
    """Document metadata by id. The caller gates access on the parent
    Entry via `accessible_entries` before serving the bytes."""
    return await session.get(MedicalDocument, document_id)


async def reassign_entries_by_patient(
    session: AsyncSession, actor: Actor, *, from_patient_id: UUID, to_patient_id: UUID
) -> list[UUID]:
    """Moves every Medical Entry from one Patient to another (P4.1, #52 —
    the merge service's write path). Returns the moved ids so the caller
    can record exactly what to move back on reversal. `actor` takes no
    part in the query — merges are Administrator-only and every function
    touching Medical Entries takes one regardless (clinical-safety.md) —
    but it is exactly what P4.3's audit emission for this path will need.
    """
    del actor
    ids_result = await session.execute(
        select(MedicalEntry.id).where(MedicalEntry.patient_id == from_patient_id)
    )
    ids = list(ids_result.scalars().all())
    if ids:
        await session.execute(
            update(MedicalEntry)
            .where(MedicalEntry.patient_id == from_patient_id)
            .values(patient_id=to_patient_id)
        )
    return ids


async def reassign_entries_by_id(
    session: AsyncSession, actor: Actor, *, entry_ids: list[UUID], to_patient_id: UUID
) -> None:
    """Reversal counterpart to `reassign_entries_by_patient` — moves an
    explicit id list rather than "everything belonging to a patient",
    since by reversal time the loser may own nothing at all."""
    del actor
    if not entry_ids:
        return
    await session.execute(
        update(MedicalEntry).where(MedicalEntry.id.in_(entry_ids)).values(patient_id=to_patient_id)
    )
