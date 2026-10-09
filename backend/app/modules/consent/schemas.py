"""Consent + break-glass wire contract.

P2.0 shipped `Consent`/`ConsentCreate`/`RevocationRequest` provisionally so
the frontend consent screens had a shape to build against; they are now
final, wired to the real service in P3.6 (#42). `BreakGlassRequest` /
`BreakGlassGrant` are new in P3.7 (#44).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import AwareDatetime, Field, field_validator, model_validator

from app.core.schema import PulseSchema
from app.modules.records.schemas import EntryType


class ConsentPurpose(StrEnum):
    TREATMENT = "TREATMENT"
    SECOND_OPINION = "SECOND_OPINION"
    OTHER = "OTHER"


class ConsentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class Consent(PulseSchema):
    id: UUID
    patient_id: UUID
    grantee_user_id: UUID
    grantee_name: str | None = None
    entry_types: list[EntryType] | None = None
    from_date: date | None = None
    to_date: date | None = None
    purpose: ConsentPurpose
    purpose_text: str | None = Field(default=None, max_length=500)
    status: ConsentStatus
    expires_at: AwareDatetime
    granted_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


class ConsentCreate(PulseSchema):
    grantee_user_id: UUID
    entry_types: list[EntryType] | None = None
    from_date: date | None = None
    to_date: date | None = None
    purpose: ConsentPurpose
    purpose_text: str | None = Field(default=None, max_length=500)
    expires_at: AwareDatetime

    @model_validator(mode="after")
    def validate_scope(self) -> ConsentCreate:
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("Date window must be ordered")
        if self.entry_types == []:
            raise ValueError("Choose at least one entry type or all types")
        if self.purpose is ConsentPurpose.OTHER and not (self.purpose_text or "").strip():
            raise ValueError("Other purpose requires an explanation")
        return self


class RevocationRequest(PulseSchema):
    reason: str | None = Field(default=None, max_length=500)


class BreakGlassRequest(PulseSchema):
    justification: str = Field(min_length=1, max_length=2000)

    @field_validator("justification")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Justification is required.")
        return value


class BreakGlassGrant(PulseSchema):
    id: UUID
    patient_id: UUID
    clinician_user_id: UUID
    justification: str
    granted_at: datetime
    expires_at: AwareDatetime


class ConsentedPatient(PulseSchema):
    """Identity-only row for a Clinician's "patients who granted me
    access" list — never a clinical field (clinical-safety.md)."""

    patient_id: UUID
    full_name: str
    expires_at: AwareDatetime


class ClinicianLookup(PulseSchema):
    """Exact-email resolution of a Clinician for the grant form — the id a
    `ConsentCreate.grantee_user_id` needs, and nothing more."""

    user_id: UUID
    email: str


@dataclass(frozen=True)
class LivePermission:
    """Immutable scope projection at the consent module's read interface."""

    id: UUID
    entry_types: list[str] | None
    from_date: date | None
    to_date: date | None
    expires_at: datetime
