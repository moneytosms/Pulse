"""Cursor pagination: opaque cursor codec plus the generic Page[T] envelope."""

import base64
import binascii
from datetime import datetime
from uuid import UUID

from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.schema import PulseSchema


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        return base64.b64decode(cursor.encode(), altchars=b"-_", validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise PulseError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid cursor.",
            http_status=422,
        ) from exc


class Page[T](PulseSchema):
    items: list[T]
    next_cursor: str | None = None


def unpack_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        ts, sep, uid = decode_cursor(cursor).partition("|")
        if not sep:
            raise ValueError("missing separator")
        when = datetime.fromisoformat(ts)
        if when.tzinfo is None or when.utcoffset() is None:
            raise ValueError("timezone required")
        return when, UUID(uid)
    except ValueError as exc:
        raise PulseError(ErrorCode.VALIDATION_ERROR, "Invalid cursor.", http_status=422) from exc
