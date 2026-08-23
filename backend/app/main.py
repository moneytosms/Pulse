"""FastAPI app: wires the core/ plumbing. No routes yet — Phase 1 mounts modules here."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from app.core.exceptions import PulseError, pulse_error_handler, validation_error_handler
from app.core.middleware import RequestIdMiddleware

app = FastAPI(title="Pulse API")

app.add_middleware(RequestIdMiddleware)

app.add_exception_handler(PulseError, pulse_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
