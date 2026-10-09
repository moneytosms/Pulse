"""FastAPI app: wires the core/ plumbing and mounts module routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException

from app.core import readiness
from app.core.access_logging import configure_access_logging
from app.core.errors import ErrorCode, ErrorEnvelope
from app.core.exceptions import (
    PulseError,
    http_error_handler,
    pulse_error_handler,
    validation_error_handler,
)
from app.core.middleware import RequestIdMiddleware
from app.core.redis import close_redis
from app.db.session import get_session
from app.modules.admin.routes import router as admin_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.audit.routes import router as audit_router
from app.modules.auth.dependencies import public
from app.modules.auth.routes import router as auth_router
from app.modules.consent.routes import router as consent_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.patients.routes import router as patients_router
from app.modules.providers.routes import router as providers_router
from app.modules.records.routes import router as records_router
from app.modules.users.routes import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_access_logging()
    yield
    await close_redis()


app = FastAPI(
    title="Pulse API",
    lifespan=lifespan,
    responses={
        code: {"model": ErrorEnvelope}
        for code in (400, 401, 403, 404, 409, 413, 422, 429, 500, 503)
    },
)

app.add_middleware(RequestIdMiddleware)
app.add_exception_handler(HTTPException, http_error_handler)

app.add_exception_handler(PulseError, pulse_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(records_router)
app.include_router(providers_router)
app.include_router(consent_router)
app.include_router(audit_router)
app.include_router(notifications_router)
app.include_router(analytics_router)
app.include_router(admin_router)
app.include_router(users_router)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/ready", dependencies=[public()])
async def ready(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    if not await readiness.check(session):
        raise PulseError(ErrorCode.INTERNAL_ERROR, "Dependencies are unavailable.", http_status=503)
    return {"status": "ready"}
