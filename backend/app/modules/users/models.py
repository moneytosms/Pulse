"""Identity models: User, Patient, Provider, ProviderStaff.

`patient.user_id` is nullable and load-bearing — a Provider files records
for someone who has never registered, who later claims the Patient
(domain-model.md, clinical-safety.md). It is not a bug.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.authz import Role
from app.db.base import Base


class Sex(StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"


class ProviderKind(StrEnum):
    HOSPITAL = "HOSPITAL"
    CLINIC = "CLINIC"
    LAB = "LAB"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(SAEnum(Role, name="role"))
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Provider(Base):
    __tablename__ = "provider"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[ProviderKind] = mapped_column(SAEnum(ProviderKind, name="provider_kind"))
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Patient(Base):
    __tablename__ = "patient"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date, default=None)
    sex: Mapped[Sex | None] = mapped_column(SAEnum(Sex, name="sex"), default=None)
    phone: Mapped[str | None] = mapped_column(String(20), default=None, index=True)
    address_line: Mapped[str | None] = mapped_column(String(255), default=None)
    city: Mapped[str | None] = mapped_column(String(120), default=None)
    state: Mapped[str | None] = mapped_column(String(120), default=None)
    locale_preference: Mapped[str] = mapped_column(String(8), default="en")
    # Tombstone for the losing side of a merge (ADR-0011). Never deleted —
    # audit events referencing this id must stay resolvable.
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), default=None, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User | None] = relationship(lazy="joined")


class ProviderStaff(Base):
    __tablename__ = "provider_staff"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        unique=True,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("provider.id", ondelete="CASCADE"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    provider: Mapped[Provider] = relationship(lazy="joined")


class ReviewStatus(StrEnum):
    PENDING = "PENDING"
    MERGED = "MERGED"
    NOT_DUPLICATE = "NOT_DUPLICATE"


class DuplicateReviewItem(Base):
    """P4.1 (#52). A pair's review status — `PENDING` until a human
    decides `MERGED` or `NOT_DUPLICATE`. A decided pair is never
    re-flagged (ADR-0011): the repository upserts on the unique
    `(patient_id_a, patient_id_b)` pair rather than inserting a new row
    each time detection runs.
    """

    __tablename__ = "duplicate_review_item"
    __table_args__ = (
        UniqueConstraint("patient_id_a", "patient_id_b", name="uq_duplicate_review_item_pair"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    patient_id_a: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    patient_id_b: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    status: Mapped[ReviewStatus] = mapped_column(String(20), default=ReviewStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("user.id"), default=None
    )


class PatientMerge(Base):
    """P4.1 (#52). The reversal record: which Patient absorbed which, who
    did it, and when. `moved_entry_ids` is every `medical_entry.id`
    reassigned from the loser to the winner, so reversal moves exactly
    those rows back rather than recomputing "what belonged to the loser".
    """

    __tablename__ = "patient_merge"

    id: Mapped[uuid.UUID] = _uuid_pk()
    winner_patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), index=True
    )
    loser_patient_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("patient.id"), index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("user.id"))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    moved_entry_ids: Mapped[list[str]] = mapped_column(JSONB)
