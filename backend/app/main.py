"""FastAPI app: wires the core/ plumbing and mounts module routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import PulseError, pulse_error_handler, validation_error_handler
from app.core.middleware import RequestIdMiddleware
from app.core.redis import close_redis
from app.modules.audit.routes import router as audit_router
from app.modules.auth.routes import router as auth_router
from app.modules.consent.routes import router as consent_router
from app.modules.notifications.routes import router as notifications_router
from app.modules.patients.routes import router as patients_router
from app.modules.providers.routes import router as providers_router
from app.modules.records.routes import router as records_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await close_redis()


app = FastAPI(title="Pulse API", lifespan=lifespan)

app.add_middleware(RequestIdMiddleware)

app.add_exception_handler(PulseError, pulse_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

app.include_router(auth_router)
app.include_router(patients_router)
app.include_router(records_router)
app.include_router(providers_router)
app.include_router(consent_router)
app.include_router(audit_router)
app.include_router(notifications_router)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
