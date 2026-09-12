"""Consent models: Consent, AccessPermission.

Consent is the Patient's agreement; AccessPermission is the live
enforcement row derived from it (domain-model.md, "Consent and
access"). They are separate tables so collapsing them never destroys
the audit trail: Consent rows are never deleted (revoking stamps
`revoked_at`), while a AccessPermission row is deleted transactionally
in the same revoke call — that delete *is* the "no cached permission"
mechanism (clinical-safety.md), not a TTL.

`AccessPermission`'s shape is spelled out in issue #37, resolving an
ambiguity domain-model.md leaves open on purpose.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.modules.consent.schemas import ConsentPurpose


class Consent(Base):
    __tablename__ = "consent"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), index=True
    )
    entry_types: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=None)
    from_date: Mapped[date | None] = mapped_column(Date, default=None)
    to_date: Mapped[date | None] = mapped_column(Date, default=None)
    purpose: Mapped[ConsentPurpose] = mapped_column(
        SAEnum(ConsentPurpose, name="consent_purpose")
    )
    purpose_text: Mapped[str | None] = mapped_column(String(500), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    revocation_reason: Mapped[str | None] = mapped_column(String(500), default=None)


class AccessPermission(Base):
    """The live enforcement row derived from an active Consent, kept lean
    so `accessible_entries` never joins back to `consent`."""

    __tablename__ = "access_permission"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    consent_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("consent.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    grantee_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), index=True
    )
    entry_types: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=None)
    from_date: Mapped[date | None] = mapped_column(Date, default=None)
    to_date: Mapped[date | None] = mapped_column(Date, default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BreakGlassAccess(Base):
    """One emergency-access grant (#41/#44, migration 0007). Break-glass is
    access *without* Consent (domain-model.md), so it cannot reuse
    `AccessPermission` — its `consent_id` is mandatory. Time-boxed to
    exactly the granted window; there is no revoke, only expiry."""

    __tablename__ = "break_glass_access"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    clinician_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), index=True
    )
    justification: Mapped[str] = mapped_column(String(2000))
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
