"""Auth business rules (G1 signatures).

No SQL, no FastAPI imports. Sessions are opaque Redis tokens (ADR-0003);
Argon2id via pwdlib. Login does NOT require a verified email — an
unverified user signs in and is gated at the permission layer instead,
so the frontend can render a "resend verification" screen.
"""

import asyncio
import os
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import IdentityProvider, VerificationOutcome
from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.rate_limit import check_limit
from app.core.security import hash_password, verify_password
from app.core.sessions import (
    create_session,
    destroy_all_sessions,
    destroy_session,
    grant_step_up,
)
from app.modules.audit import service as audit_service
from app.modules.users import service as users_service


def _normalise_email(email: str) -> str:
    return email.strip().lower()


async def register(
    session: AsyncSession,
    idp: IdentityProvider,
    *,
    email: str,
    password: str,
    role: str,
    locale: str,
) -> UUID:
    """Create the identity, start email verification. Raises on duplicate email."""
    # Only Patients self-register; Clinicians, Provider Staff and
    # Administrators are seeded. The env var exists solely so the test suite
    # can create them through this endpoint — never set it in compose.yaml.
    if Role(role) != Role.PATIENT and os.environ.get("PULSE_OPEN_ROLE_REGISTRATION") != "1":
        raise PulseError(
            ErrorCode.FORBIDDEN,
            "Only patients can register themselves.",
            http_status=403,
        )
    email = _normalise_email(email)
    _duplicate_email = PulseError(
        ErrorCode.EMAIL_ALREADY_REGISTERED,
        "That email address is already registered.",
        http_status=409,
    )
    if await users_service.get_user_by_email(session, email) is not None:
        raise _duplicate_email
    try:
        user = await users_service.register_identity(
            session,
            email=email,
            password_hash=await asyncio.to_thread(hash_password, password),
            role=Role(role),
        )
    except IntegrityError as exc:
        # The check above lost a race to a concurrent registration; the unique
        # index on user.email is the real guard. Surface the same 409.
        await session.rollback()
        raise _duplicate_email from exc
    await idp.start_verification(user.id, email, locale)
    return user.id


async def resend_verification(
    session: AsyncSession, idp: IdentityProvider, *, email: str, locale: str
) -> None:
    """Idempotent from the caller's view — never reveals whether the email exists."""
    email = _normalise_email(email)
    user = await users_service.get_user_by_email(session, email)
    if user is not None and user.email_verified_at is None:
        await idp.start_verification(user.id, email, locale)


async def complete_verification(
    session: AsyncSession, idp: IdentityProvider, *, challenge_id: str, token: str
) -> None:
    """Raises PulseError with VERIFICATION_TOKEN_INVALID / _EXPIRED on failure."""
    outcome, user_id = await idp.complete_verification(challenge_id, token)
    if outcome is VerificationOutcome.EXPIRED:
        raise PulseError(
            ErrorCode.VERIFICATION_TOKEN_EXPIRED,
            "This verification link has expired.",
            http_status=422,
        )
    if outcome is not VerificationOutcome.OK or user_id is None:
        raise PulseError(
            ErrorCode.VERIFICATION_TOKEN_INVALID,
            "This verification link is not valid.",
            http_status=422,
        )
    await users_service.mark_verified(session, user_id)


async def login(session: AsyncSession, redis: Redis, *, email: str, password: str) -> str:
    """Return a fresh session token. Raises INVALID_CREDENTIALS, generically."""
    email = _normalise_email(email)
    await check_limit(redis, "login-account", email, 10, 60)
    user = await users_service.get_user_by_email(session, email)
    if user is None or not await asyncio.to_thread(verify_password, password, user.password_hash):
        await audit_service.emit(
            session,
            actor=None,
            action=audit_service.AuditAction.LOGIN_FAILURE,
            resource_type="authentication",
            resource_id=None,
            patient_id=None,
            outcome=audit_service.AuditOutcome.DENIED,
        )
        await session.commit()
        raise PulseError(
            ErrorCode.INVALID_CREDENTIALS,
            "Email or password is incorrect.",
            http_status=401,
        )
    token = await create_session(redis, user.id, user.role)
    try:
        await audit_service.emit(
            session,
            actor=Actor(user_id=user.id, role=user.role),
            action=audit_service.AuditAction.LOGIN_SUCCESS,
            resource_type="authentication",
            resource_id=None,
            patient_id=None,
            outcome=audit_service.AuditOutcome.SUCCESS,
        )
        await session.commit()
    except Exception:
        await destroy_session(redis, token)
        raise
    return token


async def logout(session: AsyncSession, redis: Redis, token: str, actor: Actor) -> None:
    await destroy_session(redis, token)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.LOGOUT,
        resource_type="authentication",
        resource_id=None,
        patient_id=None,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    await session.commit()


async def logout_all(session: AsyncSession, redis: Redis, actor: Actor) -> None:
    await destroy_all_sessions(redis, actor.user_id)
    await audit_service.emit(
        session,
        actor=actor,
        action=audit_service.AuditAction.LOGOUT_ALL,
        resource_type="authentication",
        resource_id=None,
        patient_id=None,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    await session.commit()


async def step_up(
    session: AsyncSession,
    redis: Redis,
    *,
    token: str,
    user_id: UUID,
    password: str,
) -> None:
    """Re-verify the password and mark this session step-up'd for a short window."""
    await check_limit(redis, "step-up-account", str(user_id), 10, 60)
    user = await users_service.get_user(session, user_id)
    if user is None or not await asyncio.to_thread(verify_password, password, user.password_hash):
        await audit_service.emit(
            session,
            actor=Actor(user_id=user.id, role=user.role) if user else None,
            action=audit_service.AuditAction.STEP_UP_FAILURE,
            resource_type="authentication",
            resource_id=None,
            patient_id=None,
            outcome=audit_service.AuditOutcome.DENIED,
        )
        await session.commit()
        raise PulseError(
            ErrorCode.INVALID_CREDENTIALS,
            "Email or password is incorrect.",
            http_status=401,
        )
    await audit_service.emit(
        session,
        actor=Actor(user_id=user.id, role=user.role),
        action=audit_service.AuditAction.STEP_UP_SUCCESS,
        resource_type="authentication",
        resource_id=None,
        patient_id=None,
        outcome=audit_service.AuditOutcome.SUCCESS,
    )
    await session.commit()
    await grant_step_up(redis, token)
