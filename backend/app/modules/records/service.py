"""Clinical records business rules.

Staff attribution comes from authenticated membership. Staff may file for
existing identities, but may only correct or attach documents to their own
provider's entries. Reads compose from accessible_entries; denied and absent
resources return the same 404. Reads commit their audit before returning data;
writes commit state, audit and required in-app history together. Uploaded
bytes are deleted on database failure and verified before serving.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import NoReturn
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.storage import StorageProvider
from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.pagination import Page
from app.core.transactions import transactional
from app.modules.audit import service as audit_service
from app.modules.audit.service import AuditAction, AuditMetadata, AuditOutcome
from app.modules.notifications import service as notifications_service
from app.modules.notifications.schemas import NotificationType
from app.modules.records import access, projections, repository
from app.modules.records.models import EntryType
from app.modules.records.schemas import (
    Document,
    DocumentCreate,
    EntryCreate,
    EntryDetail,
    EntryProvider,
    EntrySummary,
    LabTest,
    LabTrendPoint,
    MedicationSummary,
    MonthlyVisitCount,
    ProviderEntryCount,
)
from app.modules.users import service as users_service

# Re-exported so other modules resolve patient access through the records
# module's own seam (the cross-module lint allows only `service`, `schemas`
# and `dependencies` to cross) — the same lookup `_authorize_entry_access`
# uses.
resolve_patient_access = access.resolve_patient_access

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


async def _authorize_entry_access(session: AsyncSession, actor: Actor, patient_id: UUID) -> None:
    """Authorize a patient relationship independently of a possibly empty
    clinical result. Membership alone is insufficient for provider staff;
    owners and clinicians with live grants may have an empty history.
    """
    resolved = await access.resolve_patient_access(session, actor, patient_id)
    if not resolved.has_any_access:
        await _deny_access(session, actor, patient_id)


def _validate_payload(payload: EntryCreate) -> None:
    missing = [
        field for field in _REQUIRED_FIELDS[payload.entry_type] if not getattr(payload, field, None)
    ]
    if missing:
        raise PulseError(
            ErrorCode.ENTRY_TYPE_MISMATCH,
            f"{payload.entry_type.value} requires {', '.join(missing)}.",
            http_status=422,
        )


@transactional
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
) -> Page[EntrySummary]:
    await _authorize_entry_access(session, actor, patient_id)
    if from_date and to_date and from_date > to_date:
        raise PulseError(
            ErrorCode.VALIDATION_ERROR, "Date window must be ordered.", http_status=422
        )
    rows, next_cursor = await repository.list_timeline(
        session,
        actor,
        patient_id,
        entry_type=entry_type,
        cursor=cursor,
        limit=limit,
        from_date=from_date,
        to_date=to_date,
        provider_id=provider_id,
        q=q,
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
    provider_names = {
        pid: await _provider_name(session, pid)
        for pid in {r.source_provider_id for r in rows}
        if pid is not None
    }
    return Page[EntrySummary](
        items=[
            projections.to_summary(
                r, provider_names.get(r.source_provider_id) if r.source_provider_id else None
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


@transactional
async def timeline_providers(
    session: AsyncSession, actor: Actor, patient_id: UUID
) -> list[EntryProvider]:
    await _authorize_entry_access(session, actor, patient_id)
    provider_ids = await repository.timeline_provider_ids(session, actor, patient_id)
    providers = []
    for provider_id in provider_ids:
        name = await _provider_name(session, provider_id)
        if name is not None:
            providers.append(EntryProvider(id=provider_id, name=name))
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ENTRY_VIEWED,
        resource_type="medical_entry",
        resource_id=None,
        patient_id=patient_id,
        outcome=AuditOutcome.SUCCESS,
        metadata=AuditMetadata(count=len(providers)),
    )
    return sorted(providers, key=lambda provider: provider.name.casefold())


@transactional
async def get_entry(session: AsyncSession, actor: Actor, entry_id: UUID) -> EntryDetail:
    entry = await repository.get_entry(session, actor, entry_id)
    if entry is None:
        await _deny_access(session, actor, entry_id)
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
    return projections.to_detail(entry, supersedes_id=supersedes_id, documents=documents)


@transactional
async def insert_entry(
    session: AsyncSession, actor: Actor, patient_id: UUID, payload: EntryCreate
) -> EntryDetail:
    """File a new Entry for a Patient. The route restricts this to Provider
    Staff (RECORDS_WRITE)."""
    patient = await users_service.get_patient(session, patient_id)
    if patient is None:
        raise _not_found()
    _validate_payload(payload)
    provider_id = await users_service.get_provider_for_staff(session, actor.user_id)
    if (
        actor.role is not Role.PROVIDER_STAFF
        or provider_id is None
        or (payload.source_provider_id is not None and payload.source_provider_id != provider_id)
    ):
        raise PulseError(
            ErrorCode.FORBIDDEN, "An associated provider is required.", http_status=403
        )
    payload = payload.model_copy(update={"source_provider_id": provider_id})
    entry = await repository.insert_entry(session, actor, patient_id, payload)
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ENTRY_CREATED,
        resource_type="medical_entry",
        resource_id=entry.id,
        patient_id=patient_id,
        outcome=AuditOutcome.SUCCESS,
    )
    fresh = await repository.get_entry(session, actor, entry.id)
    if fresh is None:  # pragma: no cover - just inserted
        raise _not_found()
    return projections.to_detail(fresh, supersedes_id=None, documents=[])


@transactional
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
    await users_service.lock_patient_for_write(session, patient_id)
    original = await repository.get_entry(session, actor, original_id)
    if original is None or original.patient_id != patient_id:
        await _deny_access(session, actor, original_id)
    _validate_payload(payload)
    provider_id = await users_service.get_provider_for_staff(session, actor.user_id)
    if (
        actor.role is not Role.PROVIDER_STAFF
        or provider_id is None
        or (payload.source_provider_id is not None and payload.source_provider_id != provider_id)
    ):
        raise PulseError(
            ErrorCode.FORBIDDEN, "An associated provider is required.", http_status=403
        )
    payload = payload.model_copy(update={"source_provider_id": provider_id})
    replacement = await repository.supersede_entry(session, actor, patient_id, original_id, payload)
    if replacement is None:
        raise PulseError(
            ErrorCode.ENTRY_ALREADY_SUPERSEDED,
            "This entry has already been corrected.",
            http_status=409,
        )
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ENTRY_CORRECTED,
        resource_type="medical_entry",
        resource_id=replacement.id,
        patient_id=patient_id,
        outcome=AuditOutcome.SUCCESS,
    )
    fresh = await repository.get_entry(session, actor, replacement.id)
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
    await users_service.lock_patient_for_write(session, patient_id)
    entry = await repository.get_entry(session, actor, entry_id)
    if entry is None or entry.patient_id != patient_id:
        await _deny_access(session, actor, entry_id)
    await _authorize_entry_access(session, actor, entry.patient_id)
    safe_name = (PurePosixPath(filename).name or "upload")[:255]
    key = f"{entry_id}/{uuid4()}-{safe_name}"
    storage_path = await storage.put(key, data, sniffed)
    meta = DocumentCreate(
        filename=safe_name,
        mime_type=sniffed,
        size_bytes=len(data),
        storage_path=storage_path,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
    )
    try:
        doc = await repository.add_document(session, actor, entry_id, meta)
        await audit_service.emit(
            session,
            actor=actor,
            action=AuditAction.DOCUMENT_UPLOADED,
            resource_type="medical_document",
            resource_id=doc.id,
            patient_id=patient_id,
            outcome=AuditOutcome.SUCCESS,
        )
        await _notify_record_uploaded(session, actor, entry.patient_id, entry_id)
        await session.commit()
    except Exception:
        await session.rollback()
        await storage.delete(storage_path)
        raise
    return projections.to_document(doc)


async def _notify_record_uploaded(
    session: AsyncSession, actor: Actor, patient_id: UUID, entry_id: UUID
) -> None:
    """In-app `RECORD_UPLOADED` for a registered Patient (`patient.user_id`
    is nullable). Params carry the entry id only — never the filename or
    any clinical content (clinical-safety.md)."""
    patient = await users_service.get_patient(session, patient_id)
    if patient is not None and patient.user_id is not None:
        await notifications_service.notify(
            session,
            patient.user_id,
            NotificationType.RECORD_UPLOADED,
            {"entryId": str(entry_id)},
        )


@transactional
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
        await _deny_access(session, actor, document_id)
    entry = await repository.get_entry(session, actor, doc.entry_id)
    if entry is None:
        await _deny_access(session, actor, doc.entry_id)
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
    try:
        data = await storage.get(doc.storage_path)
    except FileNotFoundError as exc:
        raise _not_found() from exc
    if hashlib.sha256(data).hexdigest() != doc.checksum_sha256:
        raise PulseError(
            ErrorCode.INTERNAL_ERROR, "Document integrity check failed.", http_status=500
        )
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
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    code_system: str,
    code: str,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTrendPoint]:
    return await repository.lab_trend(
        session,
        actor,
        patient_id,
        code_system=code_system,
        code=code,
        from_date=from_date,
        to_date=to_date,
    )


async def lab_tests(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[LabTest]:
    return await repository.lab_tests(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


async def visit_frequency_by_month(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MonthlyVisitCount]:
    return await repository.visit_frequency_by_month(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


async def active_medications(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[MedicationSummary]:
    return await repository.active_medications(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


async def provider_entry_counts(
    session: AsyncSession,
    actor: Actor,
    patient_id: UUID,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[ProviderEntryCount]:
    return await repository.provider_entry_counts(
        session, actor, patient_id, from_date=from_date, to_date=to_date
    )


async def future_dated_entry_count(session: AsyncSession, actor: Actor, patient_id: UUID) -> int:
    return await repository.future_dated_entry_count(session, actor, patient_id)


async def entry_count_for_patient(session: AsyncSession, actor: Actor, patient_id: UUID) -> int:
    """Administrator-only entry count, content never read (ADR-0007,
    #54's duplicate-review queue). Every other actor gets FORBIDDEN — this
    is not a general-purpose count and must not be reused as one."""
    if actor.role is not Role.ADMINISTRATOR:
        raise PulseError(
            ErrorCode.FORBIDDEN,
            "Only an Administrator may read an entry count without reading entries.",
            http_status=403,
        )
    return await repository.count_entries_for_patient(session, actor, patient_id)


async def entry_reassignment_conflicts(
    session: AsyncSession,
    actor: Actor,
    entry_ids: list[UUID],
    expected_patient_id: UUID,
    merged_at: datetime,
) -> bool:
    return await repository.entry_reassignment_conflicts(
        session, actor, entry_ids, expected_patient_id, merged_at
    )


async def authorize_patient_access(session: AsyncSession, actor: Actor, patient_id: UUID) -> None:
    await _authorize_entry_access(session, actor, patient_id)


async def _deny_access(session: AsyncSession, actor: Actor, resource_id: UUID) -> NoReturn:
    # No patient FK: a nonexistent id and a denied id have the same response.
    await audit_service.emit(
        session,
        actor=actor,
        action=AuditAction.ACCESS_DENIED,
        resource_type="clinical_resource",
        resource_id=resource_id,
        patient_id=None,
        outcome=AuditOutcome.DENIED,
    )
    await session.commit()
    raise _not_found()


async def entry_counts_for_patients(
    session: AsyncSession, actor: Actor, patient_ids: list[UUID]
) -> dict[UUID, int]:
    if actor.role is not Role.ADMINISTRATOR:
        raise PulseError(ErrorCode.FORBIDDEN, "Administrator access required.", http_status=403)
    return await repository.entry_counts_for_patients(session, actor, patient_ids)
