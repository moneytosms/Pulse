"""Identity repository — all SQL for User / Patient / Provider / ProviderStaff.

Phase 1 G1 contract: signatures merge first raising NotImplementedError,
implementations second (delivery-plan.md). Services call these; they
never build queries. Writes flush but do not commit — the calling
service owns the transaction boundary.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ColumnElement, extract, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Role
from app.modules.users.models import (
    DuplicateReviewItem,
    Patient,
    Provider,
    ProviderStaff,
    ReviewStatus,
    User,
)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def create_user(
    session: AsyncSession, *, email: str, password_hash: str, role: Role
) -> User:
    user = User(email=email, password_hash=password_hash, role=role)
    session.add(user)
    await session.flush()
    return user


async def set_password_hash(
    session: AsyncSession, user_id: UUID, password_hash: str
) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(password_hash=password_hash)
    )


async def mark_email_verified(
    session: AsyncSession, user_id: UUID, verified_at: datetime
) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(email_verified_at=verified_at)
    )


async def get_patient_by_id(session: AsyncSession, patient_id: UUID) -> Patient | None:
    return await session.get(Patient, patient_id)


async def get_patient_by_user_id(session: AsyncSession, user_id: UUID) -> Patient | None:
    result = await session.execute(select(Patient).where(Patient.user_id == user_id))
    return result.scalar_one_or_none()


async def create_patient(
    session: AsyncSession, *, user_id: UUID | None, full_name: str, **fields: object
) -> Patient:
    patient = Patient(user_id=user_id, full_name=full_name)
    for key, value in fields.items():
        setattr(patient, key, value)
    session.add(patient)
    await session.flush()
    return patient


async def set_patient_locale(
    session: AsyncSession, patient_id: UUID, locale: str
) -> None:
    await session.execute(
        update(Patient).where(Patient.id == patient_id).values(locale_preference=locale)
    )


async def get_provider_by_id(session: AsyncSession, provider_id: UUID) -> Provider | None:
    return await session.get(Provider, provider_id)


async def get_provider_staff_by_user_id(
    session: AsyncSession, user_id: UUID
) -> ProviderStaff | None:
    result = await session.execute(
        select(ProviderStaff).where(ProviderStaff.user_id == user_id)
    )
    return result.scalar_one_or_none()


# --- Duplicate detection (P4.1, #52) ---------------------------------------


async def blocked_candidates(session: AsyncSession, subject: Patient) -> list[Patient]:
    """Every Patient other than `subject` sharing a birth year, a phone,
    or a trigram hit on the (raw, un-normalised) name (database.md,
    "Duplicate detection"). `%` is pg_trgm's similarity operator —
    index-backed by `ix_patient_full_name_trgm` (migration 0008), so this
    is not a sequential scan over the whole table.
    """
    conditions: list[ColumnElement[bool]] = [Patient.full_name.op("%")(subject.full_name)]
    if subject.date_of_birth is not None:
        conditions.append(extract("year", Patient.date_of_birth) == subject.date_of_birth.year)
    if subject.phone is not None:
        conditions.append(Patient.phone == subject.phone)

    stmt = select(Patient).where(
        Patient.id != subject.id,
        Patient.merged_into_id.is_(None),
        or_(*conditions),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def upsert_review_item(
    session: AsyncSession, *, patient_id_a: UUID, patient_id_b: UUID, score: Decimal
) -> DuplicateReviewItem | None:
    """Inserts a `PENDING` review item, or refreshes the score on an
    existing `PENDING` one. A pair already decided (`MERGED` or
    `NOT_DUPLICATE`) is left untouched — decided pairs are never
    re-flagged (ADR-0011).
    """
    a, b = sorted((patient_id_a, patient_id_b), key=str)
    existing = await session.execute(
        select(DuplicateReviewItem).where(
            DuplicateReviewItem.patient_id_a == a, DuplicateReviewItem.patient_id_b == b
        )
    )
    item = existing.scalar_one_or_none()
    if item is not None:
        if item.status != ReviewStatus.PENDING:
            return None
        item.score = score
        return item

    item = DuplicateReviewItem(patient_id_a=a, patient_id_b=b, score=score)
    session.add(item)
    await session.flush()
    return item


async def set_review_status(
    session: AsyncSession,
    *,
    patient_id_a: UUID,
    patient_id_b: UUID,
    status: ReviewStatus,
    decided_by_user_id: UUID,
) -> DuplicateReviewItem:
    a, b = sorted((patient_id_a, patient_id_b), key=str)
    existing = await session.execute(
        select(DuplicateReviewItem).where(
            DuplicateReviewItem.patient_id_a == a, DuplicateReviewItem.patient_id_b == b
        )
    )
    item = existing.scalar_one_or_none()
    if item is None:
        item = DuplicateReviewItem(patient_id_a=a, patient_id_b=b, score=Decimal("0"))
        session.add(item)

    item.status = status
    item.decided_by_user_id = decided_by_user_id
    item.decided_at = datetime.now(UTC)
    await session.flush()
    return item
