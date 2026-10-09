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

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any
from uuid import UUID

from sqlalchemy import CursorResult, Select, and_, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectin_polymorphic

from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import encode_cursor, unpack_cursor
from app.modules.consent import service as consent_service
from app.modules.consent.schemas import LivePermission as LivePermission
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
from app.modules.records.schemas import (
    DocumentCreate,
    EntryCreate,
    LabTest,
    LabTrendPoint,
    MedicationSummary,
    MonthlyVisitCount,
    ProviderEntryCount,
)
from app.modules.users import service as users_service

_SUBTYPES = (Diagnosis, Prescription, LabReport, Procedure, ClinicalNote)
_MAX_LIMIT = 100


async def live_permissions_for(
    session: AsyncSession, *, patient_id: UUID, grantee_user_id: UUID
) -> list[LivePermission]:
    """LIVE `access_permission` rows for one (patient, grantee) pair —
    not expired. Revocation deletes the row transactionally
    (clinical-safety.md), so existence already means "not revoked"; the
    `expires_at` check is the rest of "live"."""
    return await consent_service.live_permissions_for(session, patient_id, grantee_user_id)


async def actor_owns_patient(session: AsyncSession, actor: Actor, patient_id: UUID) -> bool:
    """Rule 1: `actor` is the Patient identified by `patient_id`."""
    if actor.role is not Role.PATIENT:
        return False
    patient = await users_service.get_patient(session, patient_id)
    return (
        patient is not None and patient.merged_into_id is None and patient.user_id == actor.user_id
    )


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
    pair, resolved through the consent module's typed read seam."""
    return await consent_service.active_break_glass_for(session, patient_id, clinician_user_id)


async def accessible_entries(session: AsyncSession, actor: Actor, patient_id: UUID) -> Select[Any]:
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
        conditions.append(
            and_(
                MedicalEntry.patient_id == patient_id,
                consent_service.clinical_access_predicate(
                    patient_id,
                    actor.user_id,
                    MedicalEntry.entry_type.__clause_element__(),
                    MedicalEntry.occurred_at.__clause_element__(),
                ),
            )
        )

    if not conditions:
        conditions.append(false())

    return select(MedicalEntry).where(or_(*conditions))


def _pack_cursor(occurred_at: datetime, entry_id: UUID) -> str:
    return encode_cursor(f"{occurred_at.isoformat()}|{entry_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    return unpack_cursor(cursor)


async def list_timeline(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    entry_type: EntryType | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    provider_id: UUID | None = None,
    q: str | None = None,
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
    stmt = _in_window(stmt, from_date, to_date)
    if provider_id is not None:
        stmt = stmt.where(MedicalEntry.source_provider_id == provider_id)
    if q and q.strip():
        # Literal, case-insensitive search across owned subtype tables. Escaping
        # wildcard characters avoids turning a user's '%' into an all-row match.
        needle = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        matches = []
        for subtype in _SUBTYPES:
            table = subtype.__table__
            columns = [
                table.c[name]
                for name in ("display_name", "medication_name", "text")
                if name in table.c
            ]
            matches.append(
                select(table.c.id)
                .where(
                    table.c.id == MedicalEntry.id,
                    or_(*(column.ilike(f"%{needle}%", escape="\\") for column in columns)),
                )
                .exists()
            )
        stmt = stmt.where(or_(*matches))
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


async def timeline_provider_ids(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[UUID]:
    stmt = (
        (await accessible_entries(session, actor, patient_id))
        .where(
            MedicalEntry.superseded_by_id.is_(None), MedicalEntry.source_provider_id.is_not(None)
        )
        .with_only_columns(MedicalEntry.source_provider_id)
        .distinct()
    )
    rows = _bounded_rows((await session.scalars(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [row for row in rows if row is not None]


async def get_entry(session: AsyncSession, actor: Actor, entry_id: UUID) -> MedicalEntry | None:
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


async def get_superseding_original_id(session: AsyncSession, entry_id: UUID) -> UUID | None:
    """The id of the Entry that `entry_id` supersedes, if any (reverse of
    `superseded_by_id`). Non-clinical, no actor needed."""
    stmt = select(MedicalEntry.id).where(MedicalEntry.superseded_by_id == entry_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_documents(session: AsyncSession, entry_id: UUID) -> list[MedicalDocument]:
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
    await users_service.lock_patient_for_write(session, patient_id)
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
            MedicalEntry.id == original_id,
            MedicalEntry.patient_id == patient_id,
            MedicalEntry.source_provider_id == replacement_payload.source_provider_id,
            MedicalEntry.superseded_by_id.is_(None),
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
        uploaded_at=func.clock_timestamp(),
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


# --- Analytics (P4.2, #53) --------------------------------------------------
#
# Every query below starts from `accessible_entries` — there is no
# `summary_insight` table (ADR-0009), so an unauthorised or unrelated actor
# gets an empty series here for exactly the reason they get an empty
# timeline: the `or_()` in `accessible_entries` has nothing to match.


async def lab_trend(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    code_system: str,
    code: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTrendPoint]:
    """One (code_system, code)'s values over time. Vital signs have no
    separate subtype — they're LOINC-coded `lab_report` rows like any
    other observation — so this same query serves both "lab trends per
    test code" and "vital sign trends" (domain-model.md)."""
    # Joins the raw Core table (`LabReport.__table__`), not the mapped
    # class: joining the ORM entity here pulls in its *full* joined-table-
    # inheritance selectable (`medical_entry JOIN lab_report`, aliased),
    # which then has no join condition back to the outer `medical_entry`
    # from `accessible_entries` — an unconstrained cross join that
    # silently multiplies every row.
    lab_report = LabReport.__table__
    stmt = (
        _in_window(await accessible_entries(session, actor, patient_id), from_date, to_date)
        .with_only_columns(
            MedicalEntry.occurred_at,
            lab_report.c.value_numeric,
            lab_report.c.value_text,
            lab_report.c.unit,
            lab_report.c.reference_low,
            lab_report.c.reference_high,
        )
        .join(lab_report, lab_report.c.id == MedicalEntry.id)
        .where(
            MedicalEntry.entry_type == EntryType.LAB_REPORT, MedicalEntry.superseded_by_id.is_(None)
        )
        .where(lab_report.c.code_system == code_system, lab_report.c.code == code)
        .order_by(MedicalEntry.occurred_at)
    )
    rows = _bounded_rows((await session.execute(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [
        LabTrendPoint(
            occurred_at=r.occurred_at,
            value_numeric=r.value_numeric,
            value_text=r.value_text,
            unit=r.unit,
            reference_low=r.reference_low,
            reference_high=r.reference_high,
        )
        for r in rows
    ]


async def lab_tests(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTest]:
    """Each distinct (code_system, code) among the actor-visible lab
    reports, once, ordered by name — the lab-trend picker's options. Same
    raw-table join as `lab_trend`, for the same reason."""
    lab_report = LabReport.__table__
    display_name = func.max(lab_report.c.display_name)
    stmt = (
        _in_window(await accessible_entries(session, actor, patient_id), from_date, to_date)
        .with_only_columns(
            lab_report.c.code_system, lab_report.c.code, display_name, maintain_column_froms=True
        )
        .join(lab_report, lab_report.c.id == MedicalEntry.id)
        .where(
            MedicalEntry.entry_type == EntryType.LAB_REPORT, MedicalEntry.superseded_by_id.is_(None)
        )
        .group_by(lab_report.c.code_system, lab_report.c.code)
        .order_by(display_name, lab_report.c.code)
    )
    rows = _bounded_rows((await session.execute(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [LabTest(code_system=r[0], code=r[1], display_name=r[2]) for r in rows]


async def visit_frequency_by_month(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MonthlyVisitCount]:
    """Entry count per calendar month. There is no separate Visit entity
    in the domain model (domain-model.md names no such table), so a
    month's entry count stands in for visit frequency — a documented
    reading of the spec, not a modelled concept."""
    base = _in_window(
        await accessible_entries(session, actor, patient_id), from_date, to_date
    ).where(MedicalEntry.superseded_by_id.is_(None))
    sub = base.subquery()
    month_col = func.date_trunc("month", sub.c.occurred_at.op("AT TIME ZONE")("UTC"))
    stmt = (
        select(month_col.label("month"), func.count(sub.c.id).label("count"))
        .group_by(month_col)
        .order_by(month_col)
    )
    rows = _bounded_rows((await session.execute(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [MonthlyVisitCount(month=row.month.date(), count=row.count) for row in rows]


async def active_medications(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MedicationSummary]:
    """Prescriptions not superseded by a correction. Prescription carries
    no start/end date, so "active" is read as "not yet corrected away" —
    `superseded_by_id IS NULL`, the same predicate the timeline already
    uses to mean "current" (documented assumption)."""
    # Joins the raw Core table — see `lab_trend`'s comment for why the
    # mapped `Prescription` class can't be used as the join target here.
    prescription = Prescription.__table__
    stmt = (
        _in_window(await accessible_entries(session, actor, patient_id), from_date, to_date)
        .with_only_columns(
            MedicalEntry.occurred_at,
            prescription.c.medication_name,
            prescription.c.dosage,
            prescription.c.frequency,
            prescription.c.route,
        )
        .join(prescription, prescription.c.id == MedicalEntry.id)
        .where(MedicalEntry.entry_type == EntryType.PRESCRIPTION)
        .where(MedicalEntry.superseded_by_id.is_(None))
        .order_by(MedicalEntry.occurred_at.desc())
    )
    rows = _bounded_rows((await session.execute(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [
        MedicationSummary(
            occurred_at=r.occurred_at,
            medication_name=r.medication_name,
            dosage=r.dosage,
            frequency=r.frequency,
            route=r.route,
        )
        for r in rows
    ]


async def provider_entry_counts(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[ProviderEntryCount]:
    """Entry count per filing Provider — "provider upload counts"
    (domain-model.md). Counts Entries, not Documents: most Entries carry
    no Document, and the domain model has no separate "upload" concept
    to count instead (documented assumption)."""
    base = _in_window(
        await accessible_entries(session, actor, patient_id), from_date, to_date
    ).where(MedicalEntry.superseded_by_id.is_(None))
    sub = base.subquery()
    stmt = (
        select(sub.c.source_provider_id, func.count(sub.c.id).label("count"))
        .group_by(sub.c.source_provider_id)
        .order_by(func.count(sub.c.id).desc())
    )
    rows = _bounded_rows((await session.execute(stmt.limit(_MAX_SERIES_ROWS + 1))).all())
    return [ProviderEntryCount(provider_id=row.source_provider_id, count=row.count) for row in rows]


async def future_dated_entry_count(session: AsyncSession, actor: Actor, patient_id: UUID) -> int:
    """`FUTURE_DATED_ENTRY` data-quality flag material (domain-model.md,
    "Data quality"). Counted through `accessible_entries` like every
    other entry read — the flag itself is informational only and never
    exposes clinical content, but the row it counts is still a Medical
    Entry (clinical-safety.md)."""
    base = (await accessible_entries(session, actor, patient_id)).where(
        MedicalEntry.occurred_at > func.now()
    )
    result = await session.execute(select(func.count()).select_from(base.subquery()))
    return result.scalar_one()


async def count_entries_for_patient(session: AsyncSession, actor: Actor, patient_id: UUID) -> int:
    """Total Medical Entry row count for one Patient, **content never
    read**. Deliberately bypasses `accessible_entries`: ADR-0007 names
    entry counts (not entries) as exactly what the admin duplicate-review
    queue is allowed to see, and `accessible_entries` returns nothing at
    all for an Administrator actor by design, which would make every
    count zero. `actor` is accepted (and required by the actor-first lint,
    clinical-safety.md) even though it does not filter this query — the
    caller (`records.service.entry_count_for_patient`) is what enforces
    Administrator-only before this ever runs; this is not a
    general-purpose count and must never be reused with a broader actor."""
    stmt = (
        select(func.count()).select_from(MedicalEntry).where(MedicalEntry.patient_id == patient_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one()


async def provider_has_patient_entries(
    session: AsyncSession, actor: Actor, patient_id: UUID, provider_id: UUID
) -> bool:
    return bool(
        await session.scalar(
            select(MedicalEntry.id)
            .where(
                MedicalEntry.patient_id == patient_id,
                MedicalEntry.source_provider_id == provider_id,
            )
            .limit(1)
        )
    )


async def entry_reassignment_conflicts(
    session: AsyncSession,
    actor: Actor,
    entry_ids: list[UUID],
    expected_patient_id: UUID,
    merged_at: datetime,
) -> bool:
    if not entry_ids:
        return False
    rows = (
        await session.execute(
            select(MedicalEntry.id, MedicalEntry.patient_id, MedicalEntry.superseded_by_id)
            .where(MedicalEntry.id.in_(entry_ids))
            .with_for_update()
        )
    ).all()
    return (
        len(rows) != len(entry_ids)
        or any(r.patient_id != expected_patient_id for r in rows)
        or bool(
            await session.scalar(
                select(MedicalDocument.id)
                .where(
                    MedicalDocument.entry_id.in_(entry_ids),
                    MedicalDocument.uploaded_at > merged_at,
                )
                .limit(1)
            )
        )
        or bool(
            await session.scalar(
                select(MedicalEntry.id)
                .where(
                    MedicalEntry.superseded_by_id.in_(entry_ids), MedicalEntry.id.not_in(entry_ids)
                )
                .limit(1)
            )
        )
        or bool(
            await session.scalar(
                select(MedicalEntry.id)
                .where(
                    MedicalEntry.id.in_(entry_ids),
                    MedicalEntry.superseded_by_id.is_not(None),
                    MedicalEntry.superseded_by_id.not_in(entry_ids),
                )
                .limit(1)
            )
        )
    )


_MAX_SERIES_ROWS = 5000


def _in_window(stmt: Select[Any], from_date: date | None, to_date: date | None) -> Select[Any]:
    if from_date is not None:
        stmt = stmt.where(MedicalEntry.occurred_at >= datetime.combine(from_date, time.min, UTC))
    if to_date is not None:
        stmt = stmt.where(MedicalEntry.occurred_at <= datetime.combine(to_date, time.max, UTC))
    return stmt


def _bounded_rows[T](rows: Sequence[T]) -> Sequence[T]:
    if len(rows) > _MAX_SERIES_ROWS:
        raise PulseError(
            ErrorCode.ANALYTICS_WINDOW_TOO_LARGE,
            "Choose a smaller date window for this series.",
            http_status=422,
        )
    return rows


async def entry_counts_for_patients(
    session: AsyncSession, actor: Actor, patient_ids: list[UUID]
) -> dict[UUID, int]:
    rows = (
        await session.execute(
            select(MedicalEntry.patient_id, func.count(MedicalEntry.id).label("count"))
            .where(MedicalEntry.patient_id.in_(patient_ids))
            .group_by(MedicalEntry.patient_id)
        )
    ).all()
    return {row.patient_id: int(row._mapping["count"]) for row in rows}
