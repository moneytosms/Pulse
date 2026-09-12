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
    # Phase 1 — auth and identity
    EMAIL_ALREADY_REGISTERED = "EMAIL_ALREADY_REGISTERED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    EMAIL_NOT_VERIFIED = "EMAIL_NOT_VERIFIED"
    VERIFICATION_TOKEN_INVALID = "VERIFICATION_TOKEN_INVALID"
    VERIFICATION_TOKEN_EXPIRED = "VERIFICATION_TOKEN_EXPIRED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    # Phase 2 — records
    ENTRY_TYPE_MISMATCH = "ENTRY_TYPE_MISMATCH"
    ENTRY_ALREADY_SUPERSEDED = "ENTRY_ALREADY_SUPERSEDED"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    # Phase 3 — notifications
    NOTIFICATION_TYPE_MANDATORY = "NOTIFICATION_TYPE_MANDATORY"
    # Phase 3 — consent
    CONSENT_EXPIRY_OUT_OF_RANGE = "CONSENT_EXPIRY_OUT_OF_RANGE"


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
