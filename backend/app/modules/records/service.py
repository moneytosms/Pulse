"""Records business rules (P2.5).

No SQL, no FastAPI imports (backend.md). Every entry-returning function
takes an `Actor`; there are no "internal" helpers that skip it — the pure
ORM->wire mappers live in `projections.py` precisely so they are not
somewhere a filter could have been dropped.

Read access (P3.3/P3.4, #39/#40) — a Patient reads their own history; a
Provider Staff user reads entries authored by their own Provider. Writes
(`insert_entry`/`supersede_entry`) stay the Phase 2 coarse Provider Staff
allowance — any patient — pending a decision on narrowing them too. A
Clinician with no live permission, an Administrator, or an unrelated actor
gets **404, never 403**: a 403 would confirm the record exists
(clinical-safety.md). Clinician consent/break-glass matching landed in #41
(P3.5). Audit emission (P3.8, #45): `list_timeline`/`get_entry` each emit
one `ENTRY_VIEWED`, `get_document` one `DOCUMENT_VIEWED`, via
`app.modules.audit.service.emit` — never on a denied read, since a denial
never reaches `accessible_entries` in the first place. `add_document` does
not emit: it's a write (filing), not a view, and the audit action enum has
no upload-shaped value for it (`AuditAction`, `audit/models.py`).
`request_id` is not yet threaded through from the HTTP layer (no
middleware assigns one), so every `emit()` call here passes it as `None`
until that lands.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import StorageProvider
from app.core.actor import Actor
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import Page
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditAction, AuditMetadata, AuditOutcome
from app.modules.records import access, projections, repository
from app.modules.records.models import EntryType
from app.modules.records.schemas import (
    Document,
    DocumentCreate,
    EntryCreate,
    EntryDetail,
    EntrySummary,
    LabTrendPoint,
    MedicationSummary,
    MonthlyVisitCount,
    ProviderEntryCount,
)
from app.modules.users import service as users_service

# 25 MiB — larger than any scanned report; the Caddy body limit (P2.11)
# is the outer guard, this is the app-level one.
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Server-side magic-byte sniff. The declared Content-Type and the file
# extension are both attacker-controlled (backend.md), so the allowlist is
# checked against the actual bytes.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"%PDF", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)


def _sniff_mime(data: bytes) -> str | None:
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    return None

_REQUIRED_FIELDS: dict[EntryType, tuple[str, ...]] = {
    EntryType.DIAGNOSIS: ("code_system", "code", "display_name"),
    EntryType.PROCEDURE: ("code_system", "code", "display_name"),
    EntryType.LAB_REPORT: ("code_system", "code", "display_name"),
    EntryType.PRESCRIPTION: ("medication_name",),
    EntryType.CLINICAL_NOTE: ("text",),
}


def _not_found() -> PulseError:
    return PulseError(ErrorCode.NOT_FOUND, "No such record.", http_status=404)


async def _provider_name(session: AsyncSession, provider_id: UUID | None) -> str | None:
    """Provider display name for the audit projection's `provider_name`
    (not clinical content — a Provider's public identity, `PROVIDER_READ`
    is open to every signed-in role). None when the Entry carries no
    `source_provider_id`."""
    if provider_id is None:
        return None
    provider = await users_service.get_provider(session, provider_id)
    return provider.name if provider is not None else None


async def _authorize_entry_access(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> None:
    """P3.3/P3.4 (#39, #40) access — rules 1–2 via `access.resolve_patient_access`.

    This is the identity gate ("does `actor` have any relationship to this
    patient at all"), not `repository.accessible_entries` itself —
    `accessible_entries` decides which *entries* are visible and would
    wrongly 404 a Patient or Provider Staff member whose history is
    genuinely empty. Both are built from the same rule-1/rule-2 lookups
    (`repository.actor_owns_patient` / `provider_id_for_staff_actor`), so
    they can't drift apart. Everyone else — Clinician with no live
    permission yet, Administrator, an unrelated Patient — gets 404, never
    403 (clinical-safety.md, ADR-0007). Rules 3–4 land in #41 (P3.5).
    """
    resolved = await access.resolve_patient_access(session, actor, patient_id)
    if not resolved.has_any_access:
        raise _not_found()


def _validate_payload(payload: EntryCreate) -> None:
    missing = [
        field
        for field in _REQUIRED_FIELDS[payload.entry_type]
        if not getattr(payload, field, None)
    ]
    if missing:
        raise PulseError(
            ErrorCode.ENTRY_TYPE_MISMATCH,
            f"{payload.entry_type.value} requires {', '.join(missing)}.",
            http_status=422,
        )


async def list_timeline(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    entry_type: EntryType | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[EntrySummary]:
    await _authorize_entry_access(session, actor, patient_id)
    rows, next_cursor = await repository.list_timeline(
        session, actor, patient_id, entry_type=entry_type, cursor=cursor, limit=limit
    )
    # One ENTRY_VIEWED per call regardless of page size (#45 acceptance) —
    # this describes the query, not a row, so `resource_id` is patient-level
    # (None) and the entry-type filter (when the caller narrowed by one) is
    # the only per-request detail worth keeping.
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=None,
        patient_id=patient_id,
        outcome=AuditOutcome.SUCCESS,
        metadata=AuditMetadata(
            entry_type=entry_type.value if entry_type is not None else None,
            count=len(rows),
        ),
    )
    return Page[EntrySummary](
        items=[projections.to_summary(r) for r in rows], next_cursor=next_cursor
    )


async def get_entry(session: AsyncSession, actor: Actor, entry_id: UUID) -> EntryDetail:
    entry = await repository.get_entry(session, actor, entry_id)
    if entry is None:
        raise _not_found()
    await _authorize_entry_access(session, actor, entry.patient_id)
    supersedes_id = await repository.get_superseding_original_id(session, entry_id)
    documents = await repository.list_documents(session, entry_id)
    provider_name = await _provider_name(session, entry.source_provider_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=entry.id,
        patient_id=entry.patient_id,
        outcome=AuditOutcome.SUCCESS,
        metadata=AuditMetadata(entry_type=entry.entry_type.value, provider_name=provider_name),
    )
    return projections.to_detail(
        entry, supersedes_id=supersedes_id, documents=documents
    )


async def insert_entry(
    session: AsyncSession, actor: Actor, patient_id: UUID, payload: EntryCreate
) -> EntryDetail:
    """File a new Entry for a Patient. The route restricts this to Provider
    Staff (RECORDS_WRITE)."""
    patient = await users_service.get_patient(session, patient_id)
    if patient is None:
        raise _not_found()
    _validate_payload(payload)
    if payload.source_provider_id is None:
        provider_id = await users_service.get_provider_for_staff(
            session, actor.user_id
        )
        payload = payload.model_copy(update={"source_provider_id": provider_id})
    entry = await repository.insert_entry(session, actor, patient_id, payload)
    await session.commit()
    fresh = await repository.get_entry_unfiltered(session, actor, entry.id)
    if fresh is None:  # pragma: no cover - just inserted
        raise _not_found()
    return projections.to_detail(fresh, supersedes_id=None, documents=[])


async def supersede_entry(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    original_id: UUID,
    payload: EntryCreate,
) -> EntryDetail:
    """Correction path (P2.7): insert a new Entry, stamp `superseded_by_id`
    on the original. Never an in-place update of clinical data. The route
    restricts this to Provider Staff (RECORDS_WRITE)."""
    if await users_service.get_patient(session, patient_id) is None:
        raise _not_found()
    original = await repository.get_entry_unfiltered(session, actor, original_id)
    if original is None or original.patient_id != patient_id:
        raise _not_found()
    _validate_payload(payload)
    if payload.source_provider_id is None:
        provider_id = await users_service.get_provider_for_staff(
            session, actor.user_id
        )
        payload = payload.model_copy(update={"source_provider_id": provider_id})
    replacement = await repository.supersede_entry(
        session, actor, patient_id, original_id, payload
    )
    if replacement is None:
        raise PulseError(
            ErrorCode.ENTRY_ALREADY_SUPERSEDED,
            "This entry has already been corrected.",
            http_status=409,
        )
    await session.commit()
    fresh = await repository.get_entry_unfiltered(session, actor, replacement.id)
    if fresh is None:  # pragma: no cover - just inserted
        raise _not_found()
    return projections.to_detail(fresh, supersedes_id=original_id, documents=[])


async def add_document(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    entry_id: UUID,
    *,
    storage: StorageProvider,
    data: bytes,
    filename: str,
) -> Document:
    """Attach an uploaded file to an Entry. Size cap first (413), then a
    server-side magic-byte sniff against the allowlist (422), then store
    the bytes and record the checksum. Provider Staff only (route guard)."""
    if len(data) > _MAX_UPLOAD_BYTES:
        raise PulseError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            "The file exceeds the upload size limit.",
            http_status=413,
        )
    sniffed = _sniff_mime(data)
    if sniffed is None:
        raise PulseError(
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "Only PDF, PNG and JPEG documents are accepted.",
            http_status=422,
        )
    entry = await repository.get_entry(session, actor, entry_id)
    if entry is None or entry.patient_id != patient_id:
        raise _not_found()
    await _authorize_entry_access(session, actor, entry.patient_id)
    safe_name = PurePosixPath(filename).name or "upload"
    key = f"{entry_id}/{uuid4()}-{safe_name}"
    storage_path = await storage.put(key, data, sniffed)
    meta = DocumentCreate(
        filename=safe_name,
        mime_type=sniffed,
        size_bytes=len(data),
        storage_path=storage_path,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )
    doc = await repository.add_document(session, actor, entry_id, meta)
    await session.commit()
    return projections.to_document(doc)


async def get_document(
    session: AsyncSession,
    actor: Actor,
    document_id: UUID,
    *,
    storage: StorageProvider,
) -> tuple[Document, bytes]:
    """Document metadata + bytes, behind the same access rule as its
    Entry — a denied caller gets 404, never a hint that it exists."""
    doc = await repository.get_document(session, actor, document_id)
    if doc is None:
        raise _not_found()
    entry = await repository.get_entry(session, actor, doc.entry_id)
    if entry is None:
        raise _not_found()
    await _authorize_entry_access(session, actor, entry.patient_id)
    provider_name = await _provider_name(session, entry.source_provider_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.DOCUMENT_VIEWED,
        resource_type="medical_document",
        resource_id=doc.id,
        patient_id=entry.patient_id,
        outcome=AuditOutcome.SUCCESS,
        metadata=AuditMetadata(entry_type=entry.entry_type.value, provider_name=provider_name),
    )
    data = await storage.get(doc.storage_path)
    return projections.to_document(doc), data


async def reassign_patient_entries(
    session: AsyncSession, actor: Actor, *, from_patient_id: UUID, to_patient_id: UUID
) -> list[UUID]:
    """P4.1 (#52) merge write path — the only way another module may move
    Medical Entries between Patients. No access check here: the caller
    (the merge service) is itself the access-controlled boundary."""
    return await repository.reassign_entries_by_patient(
        session, actor, from_patient_id=from_patient_id, to_patient_id=to_patient_id
    )


async def reverse_entry_reassignment(
    session: AsyncSession, actor: Actor, *, entry_ids: list[UUID], to_patient_id: UUID
) -> None:
    await repository.reassign_entries_by_id(
        session, actor, entry_ids=entry_ids, to_patient_id=to_patient_id
    )


# --- Analytics (P4.2, #53) --------------------------------------------------
#
# Thin pass-throughs: the query logic lives in repository.py, this
# module's one and only Medical-Entry query builder (ADR-0006). No audit
# emission yet — that lands with P4.3's analytics-on-read composition.


async def lab_trend(
    session: AsyncSession, actor: Actor, patient_id: UUID, *, code_system: str, code: str
) -> list[LabTrendPoint]:
    return await repository.lab_trend(
        session, actor, patient_id, code_system=code_system, code=code
    )


async def visit_frequency_by_month(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[MonthlyVisitCount]:
    return await repository.visit_frequency_by_month(session, actor, patient_id)


async def active_medications(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[MedicationSummary]:
    return await repository.active_medications(session, actor, patient_id)


async def provider_entry_counts(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[ProviderEntryCount]:
    return await repository.provider_entry_counts(session, actor, patient_id)


async def future_dated_entry_count(session: AsyncSession, actor: Actor, patient_id: UUID) -> int:
    return await repository.future_dated_entry_count(session, actor, patient_id)
