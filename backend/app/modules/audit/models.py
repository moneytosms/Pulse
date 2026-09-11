"""Audit models: AuditEvent.

Append-only by database GRANT, not convention (ADR-0008) — `pulse_app`
holds INSERT/SELECT only on `audit_event`, enforced in migration 0005.
`event_metadata` maps the `metadata` column (reserved on a Declarative
class, same reason as `MedicalEntry.entry_metadata`). It holds
identifiers, counts, entry types and the break-glass justification —
never clinical content (clinical-safety.md, domain-model.md).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.authz import Role
from app.db.base import Base


class AuditAction(StrEnum):
    ENTRY_VIEWED = "ENTRY_VIEWED"
    DOCUMENT_VIEWED = "DOCUMENT_VIEWED"
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    BREAK_GLASS_ACCESS = "BREAK_GLASS_ACCESS"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"


class AuditOutcome(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    # Denormalised at write time — roles change, history must not.
    actor_role: Mapped[Role] = mapped_column(SAEnum(Role, name="role"))
    action: Mapped[AuditAction] = mapped_column(SAEnum(AuditAction, name="audit_action"))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), default=None)
    patient_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("patient.id", ondelete="SET NULL"),
        default=None,
        index=True,
    )
    outcome: Mapped[AuditOutcome] = mapped_column(SAEnum(AuditOutcome, name="audit_outcome"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip: Mapped[str | None] = mapped_column(String(64), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(512), default=None)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
