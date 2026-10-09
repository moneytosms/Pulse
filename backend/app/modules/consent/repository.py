"""Consent + break-glass repository — all SQL for this module.

`create_consent_and_permission` writes both rows `AccessPermission`'s
docstring describes: the `Consent` record and the live `access_permission`
row derived from it, in one flush so the caller commits them together.
`revoke_consent` stamps `revoked_at`/`revocation_reason` and deletes the
`access_permission` row in the same flush — that delete *is* the "no
cached permission" mechanism (clinical-safety.md), not a TTL.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import ColumnElement, Date, String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement as Expression

from app.core.pagination import encode_cursor, unpack_cursor
from app.modules.consent.models import AccessPermission, BreakGlassAccess, Consent
from app.modules.consent.schemas import ConsentPurpose

_MAX_LIMIT = 100


def _pack_cursor(granted_at: datetime, consent_id: UUID) -> str:
    return encode_cursor(f"{granted_at.isoformat()}|{consent_id}")


def _unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    return unpack_cursor(cursor)


async def get_consent_by_id(session: AsyncSession, consent_id: UUID) -> Consent | None:
    return (
        await session.scalars(
            select(Consent)
            .where(Consent.id == consent_id)
            .with_for_update(of=Consent)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()


async def create_consent_and_permission(
    session: AsyncSession,
    *,
    patient_id: UUID,
    grantee_user_id: UUID,
    entry_types: list[str] | None,
    from_date: date | None,
    to_date: date | None,
    purpose: ConsentPurpose,
    purpose_text: str | None,
    expires_at: datetime,
) -> Consent:
    consent = Consent(
        patient_id=patient_id,
        grantee_user_id=grantee_user_id,
        entry_types=entry_types,
        from_date=from_date,
        to_date=to_date,
        purpose=purpose,
        purpose_text=purpose_text,
        expires_at=expires_at,
    )
    session.add(consent)
    await session.flush()
    permission = AccessPermission(
        consent_id=consent.id,
        patient_id=patient_id,
        grantee_user_id=grantee_user_id,
        entry_types=entry_types,
        from_date=from_date,
        to_date=to_date,
        expires_at=expires_at,
    )
    session.add(permission)
    await session.flush()
    return consent


async def revoke_consent(
    session: AsyncSession, consent_id: UUID, *, reason: str | None, revoked_at: datetime
) -> Consent | None:
    """Returns None when there is no such consent, or it is already
    revoked — revocation is not repeatable."""
    consent = (
        await session.scalars(
            select(Consent)
            .where(Consent.id == consent_id)
            .with_for_update(of=Consent)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    if consent is None or consent.revoked_at is not None:
        return None
    consent.revoked_at = revoked_at
    consent.revocation_reason = reason
    await session.execute(delete(AccessPermission).where(AccessPermission.consent_id == consent_id))
    await session.flush()
    return consent


async def list_consents_for_patient(
    session: AsyncSession,
    patient_id: UUID,
    *,
    cursor: str | None,
    limit: int,
    view: Literal["active", "history"] | None = None,
) -> tuple[list[Consent], str | None]:
    limit = max(1, min(limit, _MAX_LIMIT))
    stmt = select(Consent).where(Consent.patient_id == patient_id)
    active = (Consent.revoked_at.is_(None)) & (Consent.expires_at > func.statement_timestamp())
    if view == "active":
        stmt = stmt.where(active)
    elif view == "history":
        stmt = stmt.where(~active)
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        stmt = stmt.where(
            or_(
                Consent.granted_at < c_at,
                (Consent.granted_at == c_at) & (Consent.id < c_id),
            )
        )
    stmt = stmt.order_by(Consent.granted_at.desc(), Consent.id.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.granted_at, tail.id)
    return rows, next_cursor


async def list_live_permissions_for_grantee(
    session: AsyncSession, grantee_user_id: UUID, *, now: datetime, cursor: str | None, limit: int
) -> tuple[list[AccessPermission], str | None]:
    limit = max(1, min(limit, _MAX_LIMIT))
    stmt = select(AccessPermission).where(
        AccessPermission.grantee_user_id == grantee_user_id,
        AccessPermission.expires_at > now,
    )
    if cursor is not None:
        c_at, c_id = _unpack_cursor(cursor)
        stmt = stmt.where(
            or_(
                AccessPermission.created_at < c_at,
                (AccessPermission.created_at == c_at) & (AccessPermission.id < c_id),
            )
        )
    stmt = stmt.order_by(AccessPermission.created_at.desc(), AccessPermission.id.desc()).limit(
        limit + 1
    )
    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        tail = rows[-1]
        next_cursor = _pack_cursor(tail.created_at, tail.id)
    return rows, next_cursor


async def create_break_glass(
    session: AsyncSession,
    *,
    patient_id: UUID,
    clinician_user_id: UUID,
    justification: str,
    expires_at: datetime,
) -> BreakGlassAccess:
    grant = BreakGlassAccess(
        patient_id=patient_id,
        clinician_user_id=clinician_user_id,
        justification=justification,
        expires_at=expires_at,
    )
    session.add(grant)
    await session.flush()
    return grant


def clinical_access_predicate(
    patient_id: UUID,
    grantee_user_id: UUID,
    entry_type: Expression[Any],
    occurred_at: Expression[Any],
) -> ColumnElement[bool]:
    permission = (
        select(AccessPermission.id)
        .where(
            AccessPermission.patient_id == patient_id,
            AccessPermission.grantee_user_id == grantee_user_id,
            AccessPermission.expires_at > func.statement_timestamp(),
            or_(
                AccessPermission.entry_types.is_(None),
                cast(entry_type, String) == func.any(AccessPermission.entry_types),
            ),
            or_(
                AccessPermission.from_date.is_(None),
                cast(occurred_at.op("AT TIME ZONE")("UTC"), Date) >= AccessPermission.from_date,
            ),
            or_(
                AccessPermission.to_date.is_(None),
                cast(occurred_at.op("AT TIME ZONE")("UTC"), Date) <= AccessPermission.to_date,
            ),
        )
        .correlate_except(AccessPermission)
        .exists()
    )
    emergency = (
        select(BreakGlassAccess.id)
        .where(
            BreakGlassAccess.patient_id == patient_id,
            BreakGlassAccess.clinician_user_id == grantee_user_id,
            BreakGlassAccess.expires_at > func.statement_timestamp(),
        )
        .exists()
    )
    return or_(permission, emergency)


async def live_permissions_for(
    session: AsyncSession, patient_id: UUID, grantee_user_id: UUID
) -> list[AccessPermission]:
    return list(
        (
            await session.scalars(
                select(AccessPermission).where(
                    AccessPermission.patient_id == patient_id,
                    AccessPermission.grantee_user_id == grantee_user_id,
                    AccessPermission.expires_at > func.statement_timestamp(),
                )
            )
        ).all()
    )


async def active_break_glass_for(
    session: AsyncSession, patient_id: UUID, clinician_user_id: UUID
) -> bool:
    return bool(
        await session.scalar(
            select(BreakGlassAccess.id)
            .where(
                BreakGlassAccess.patient_id == patient_id,
                BreakGlassAccess.clinician_user_id == clinician_user_id,
                BreakGlassAccess.expires_at > func.statement_timestamp(),
            )
            .limit(1)
        )
    )


async def has_live_patient_grants(session: AsyncSession, patient_id: UUID) -> bool:
    permission = (
        select(AccessPermission.id)
        .where(
            AccessPermission.patient_id == patient_id,
            AccessPermission.expires_at > func.statement_timestamp(),
        )
        .exists()
    )
    emergency = (
        select(BreakGlassAccess.id)
        .where(
            BreakGlassAccess.patient_id == patient_id,
            BreakGlassAccess.expires_at > func.statement_timestamp(),
        )
        .exists()
    )
    return bool(await session.scalar(select(or_(permission, emergency))))
