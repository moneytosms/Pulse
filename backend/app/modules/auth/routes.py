"""Auth HTTP surface. HTTP only — parse, validate, delegate to service.

Endpoints:
  POST /api/v1/auth/register         public
  POST /api/v1/auth/verify/resend    public
  POST /api/v1/auth/verify           public
  POST /api/v1/auth/login            public
  POST /api/v1/auth/logout           requires(..., verified=False)
  POST /api/v1/auth/logout-all       requires(..., verified=False)
  POST /api/v1/auth/step-up          requires(..., verified=False)
  GET  /api/v1/auth/me               requires(..., verified=False)

The session-management routes pass `verified=False`: an unverified user holds
a valid session and must be able to read their own state and end it. Every
role holds USER_CREDENTIALS_CHANGE, so it stands in for "any authenticated
user" until a dedicated marker is needed.

Every route declares `public()` or `requires(...)` in its `dependencies=`.
"""

import os
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.identity import IdentityProvider
from app.core.authz import Permission
from app.core.redis import get_redis
from app.db.session import get_session
from app.modules.auth import service
from app.modules.auth.dependencies import (
    SESSION_COOKIE,
    AuthContext,
    current_user,
    get_identity_provider,
    public,
    requires,
    throttled,
)
from app.modules.auth.schemas import (
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RegisterResponse,
    ResendVerificationRequest,
    StepUpRequest,
    VerifyRequest,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
IdpDep = Annotated[IdentityProvider, Depends(get_identity_provider)]
CurrentUser = Annotated[AuthContext, Depends(current_user)]


def _set_session_cookie(response: Response, token: str) -> None:
    # No Max-Age: a session cookie whose real lifetime is the server-side Redis
    # record — sliding 60-minute idle, hard 12-hour cap (ADR-0003, sessions.py).
    # A fixed Max-Age here would expire the cookie mid-session and never let the
    # sliding refresh or the absolute cap be the binding limit.
    response.set_cookie(
        SESSION_COOKIE,
        token,
        path="/",
        httponly=True,
        samesite="lax",
        secure=os.environ.get("PULSE_SECURE_COOKIES") == "1",
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    dependencies=[public(), throttled("register", limit=20, window=3600)],
)
async def register(body: RegisterRequest, session: SessionDep, idp: IdpDep) -> RegisterResponse:
    user_id = await service.register(
        session,
        idp,
        email=body.email,
        password=body.password,
        role=body.role.value,
        locale="en",
    )
    return RegisterResponse(user_id=user_id)


@router.post(
    "/verify/resend",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[public(), throttled("resend", limit=20, window=3600)],
)
async def resend_verification(
    body: ResendVerificationRequest, session: SessionDep, idp: IdpDep
) -> dict[str, str]:
    await service.resend_verification(session, idp, email=body.email, locale="en")
    return {}


@router.post("/verify", dependencies=[public(), throttled("verify", limit=30)])
async def verify(body: VerifyRequest, session: SessionDep, idp: IdpDep) -> dict[str, str]:
    await service.complete_verification(
        session, idp, challenge_id=body.challenge_id, token=body.token
    )
    return {}


@router.post("/login", dependencies=[public(), throttled("login", limit=60)])
async def login(
    body: LoginRequest, response: Response, session: SessionDep, redis: RedisDep
) -> dict[str, str]:
    token = await service.login(session, redis, email=body.email, password=body.password)
    _set_session_cookie(response, token)
    return {}


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires(Permission.USER_CREDENTIALS_CHANGE, verified=False)],
)
async def logout(
    response: Response, ctx: CurrentUser, redis: RedisDep, session: SessionDep
) -> None:
    await service.logout(session, redis, ctx.session_token, ctx.actor)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[requires(Permission.USER_CREDENTIALS_CHANGE, verified=False)],
)
async def logout_all(
    response: Response, ctx: CurrentUser, redis: RedisDep, session: SessionDep
) -> None:
    await service.logout_all(session, redis, ctx.actor)
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post(
    "/step-up",
    dependencies=[requires(Permission.USER_CREDENTIALS_CHANGE, verified=False)],
)
async def step_up(
    body: StepUpRequest, ctx: CurrentUser, session: SessionDep, redis: RedisDep
) -> dict[str, str]:
    await service.step_up(
        session,
        redis,
        token=ctx.session_token,
        user_id=ctx.user_id,
        password=body.password,
    )
    return {}


@router.get(
    "/me",
    dependencies=[requires(Permission.USER_CREDENTIALS_CHANGE, verified=False)],
)
async def me(ctx: CurrentUser) -> MeResponse:
    return MeResponse(
        user_id=ctx.user_id,
        role=ctx.role,
        email=ctx.email,
        email_verified=ctx.email_verified,
    )
