"""Records wire contract (G1).

`EntrySummary` is one timeline row; `EntryDetail` adds the subtype-specific
fields, all optional because they vary by `entryType`. Clinical content is
never translated — display names and note text render as recorded
(clinical-safety.md). These schemas are real and reused by the P2.3/P2.5
implementation; only the `@stub` fixtures behind them are throwaway.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from app.core.schema import PulseSchema
from app.modules.records.models import EntryType


class EntrySummary(PulseSchema):
    id: UUID
    patient_id: UUID
    entry_type: EntryType
    occurred_at: datetime
    recorded_at: datetime
    is_critical: bool = False
    superseded_by_id: UUID | None = None
    source_provider_id: UUID | None = None
    # A short human label for the row — the diagnosis/lab/medication name, or
    # a note snippet. Recorded text, never translated.
    summary: str | None = None


class Document(PulseSchema):
    id: UUID
    entry_id: UUID
    filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    uploaded_at: datetime


class EntryDetail(EntrySummary):
    metadata: dict[str, Any] = {}
    supersedes_id: UUID | None = None
    documents: list[Document] = []
    # coded subtypes (diagnosis, procedure, lab_report, prescription)
    code_system: str | None = None
    code: str | None = None
    display_name: str | None = None
    # lab_report
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    # prescription
    medication_name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    # clinical_note
    text: str | None = None


class EntryCreate(PulseSchema):
    """What a Provider files, or what a correction re-files (P2.5 / P2.7).

    Subtype fields are optional at the wire; the service validates the set
    required for `entry_type`. There is deliberately no `metadata` field —
    `medical_entry.metadata` is provenance only and set by the import
    pipeline, never by an API caller (clinical-safety.md: no clinical value
    in JSONB, "not temporarily").
    """

    entry_type: EntryType
    occurred_at: datetime
    is_critical: bool = False
    source_provider_id: UUID | None = None
    code_system: str | None = None
    code: str | None = None
    display_name: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None
    medication_name: str | None = None
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None
    text: str | None = None


class DocumentCreate(PulseSchema):
    """Stored-file metadata handed to the repository after the bytes land
    behind the StorageProvider (P2.6). No clinical content."""

    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    checksum_sha256: str


class LabTrendPoint(PulseSchema):
    """One point in a lab/vital-sign trend (P4.2, #53). Vital signs have
    no separate subtype — Synthea observations, vitals included, land as
    `lab_report` rows (LOINC-coded), so this same shape serves both of
    domain-model.md's "lab trends per test code" and "vital sign trends"
    series."""

    occurred_at: datetime
    value_numeric: float | None = None
    value_text: str | None = None
    unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None


class MonthlyVisitCount(PulseSchema):
    """One month's entry count — the "visit frequency by month" series.
    There is no separate Visit entity in the domain model, so a month's
    entry count stands in for it (documented assumption, not a modelled
    concept)."""

    month: date
    count: int


class MedicationSummary(PulseSchema):
    """One row of the "active medications" series — a Prescription not
    superseded by a correction. There is no explicit start/end date on
    Prescription, so "active" is read as "not yet corrected away"
    (documented assumption — `superseded_by_id IS NULL`, the same
    predicate the timeline already uses to mean "current")."""

    occurred_at: datetime
    medication_name: str
    dosage: str | None = None
    frequency: str | None = None
    route: str | None = None


class ProviderEntryCount(PulseSchema):
    """One Provider's entry count — the "provider upload counts" series.
    Counts Medical Entries attributed to a Provider (`source_provider_id`),
    not Documents specifically: most Entries carry no Document, and the
    domain model has no separate "upload" concept to count instead."""

    provider_id: UUID | None
    count: int
