"""Error codes and the error envelope. Codes are stable forever, never reworded."""

from enum import StrEnum

from app.core.schema import PulseSchema


class ErrorCode(StrEnum):
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    CONFLICT = "CONFLICT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(PulseSchema):
    field: str | None = None
    code: str | None = None


class ErrorBody(PulseSchema):
    code: ErrorCode
    message: str
    details: list[ErrorDetail] = []
    request_id: str | None = None


class ErrorEnvelope(PulseSchema):
    error: ErrorBody
