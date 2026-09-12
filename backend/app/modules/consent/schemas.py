"""Consent + break-glass wire contract.

P2.0 shipped `Consent`/`ConsentCreate`/`RevocationRequest` provisionally so
the frontend consent screens had a shape to build against; they are now
final, wired to the real service in P3.6 (#42). `BreakGlassRequest` /
`BreakGlassGrant` are new in P3.7 (#44).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schema import PulseSchema


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
    entry_types: list[str] | None = None
    from_date: date | None = None
    to_date: date | None = None
    purpose: ConsentPurpose
    purpose_text: str | None = None
    status: ConsentStatus
    expires_at: datetime
    granted_at: datetime
    revoked_at: datetime | None = None
    revocation_reason: str | None = None


class ConsentCreate(PulseSchema):
    grantee_user_id: UUID
    entry_types: list[str] | None = None
    from_date: date | None = None
    to_date: date | None = None
    purpose: ConsentPurpose
    purpose_text: str | None = None
    expires_at: datetime


class RevocationRequest(PulseSchema):
    reason: str | None = None


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
    expires_at: datetime
