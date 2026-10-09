"""ORM -> wire projections for the records module.

Pure functions, no SQL, no access logic — they never see an `Actor` and
must never be a place a filter could have been applied. Kept out of
`service.py` so the actor-first lint's target stays the functions that
actually compose reads.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.modules.records.models import MedicalDocument, MedicalEntry
from app.modules.records.schemas import Document, EntryDetail, EntrySummary


def _num(value: Any) -> float | None:
    return float(value) if value is not None else None


def summary_text(entry: MedicalEntry) -> str | None:
    for attr in ("display_name", "medication_name"):
        text = getattr(entry, attr, None)
        if text:
            return str(text)
    note = getattr(entry, "text", None)
    return str(note)[:120] if note else None


def to_summary(entry: MedicalEntry, provider_name: str | None = None) -> EntrySummary:
    return EntrySummary(
        id=entry.id,
        patient_id=entry.patient_id,
        entry_type=entry.entry_type,
        occurred_at=entry.occurred_at,
        recorded_at=entry.recorded_at,
        is_critical=entry.is_critical,
        superseded_by_id=entry.superseded_by_id,
        source_provider_id=entry.source_provider_id,
        provider_name=provider_name,
        summary=summary_text(entry),
    )


def to_document(doc: MedicalDocument) -> Document:
    return Document(
        id=doc.id,
        entry_id=doc.entry_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        checksum_sha256=doc.checksum_sha256,
        uploaded_at=doc.uploaded_at,
    )


def to_detail(
    entry: MedicalEntry,
    *,
    supersedes_id: UUID | None,
    documents: list[MedicalDocument],
) -> EntryDetail:
    def g(name: str) -> Any:
        return getattr(entry, name, None)

    return EntryDetail(
        **to_summary(entry).model_dump(),
        metadata=entry.entry_metadata or {},
        supersedes_id=supersedes_id,
        documents=[to_document(d) for d in documents],
        code_system=g("code_system"),
        code=g("code"),
        display_name=g("display_name"),
        value_numeric=_num(g("value_numeric")),
        value_text=g("value_text"),
        unit=g("unit"),
        reference_low=_num(g("reference_low")),
        reference_high=_num(g("reference_high")),
        medication_name=g("medication_name"),
        dosage=g("dosage"),
        frequency=g("frequency"),
        route=g("route"),
        text=g("text"),
    )
