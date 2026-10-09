"""Request-id middleware: generates/propagates X-Request-Id, stashed in a contextvar."""

import logging
import re
import uuid
from contextvars import ContextVar
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# A client-supplied id is kept only if it fits `audit_event.request_id`
# (String(64)) and is plain token characters; anything else is replaced.
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,64}")

_request_context: ContextVar[tuple[str | None, str | None]] = ContextVar(
    "request_context", default=(None, None)
)


def get_request_context() -> tuple[str | None, str | None]:
    return _request_context.get()


_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied = request.headers.get("X-Request-Id", "")
        request_id = supplied if _VALID_REQUEST_ID.fullmatch(supplied) else str(uuid.uuid4())
        token = _request_id.set(request_id)
        response: Response
        context_token = _request_context.set(
            (
                request.client.host if request.client else None,
                request.headers.get("User-Agent", "")[:512] or None,
            )
        )
        request.state.request_id = request_id
        try:
            from app.core.errors import ErrorCode
            from app.core.exceptions import _envelope_response

            origin = request.headers.get("Origin")
            if request.method not in {"GET", "HEAD", "OPTIONS"} and (
                (origin and urlsplit(origin).netloc != request.headers.get("Host"))
                or request.headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                response = _envelope_response(
                    403, ErrorCode.FORBIDDEN, "Use the application's origin for this request."
                )
            else:
                response = await call_next(request)
        except Exception as error:
            logging.getLogger(__name__).error(
                "Unhandled request failure request_id=%s type=%s",
                request_id,
                type(error).__name__,
            )
            response = _envelope_response(
                500, ErrorCode.INTERNAL_ERROR, "The request could not be completed."
            )
        finally:
            _request_id.reset(token)
            _request_context.reset(context_token)
        response.headers["X-Request-Id"] = request_id
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response
