"""Cursor pagination: opaque cursor codec plus the generic Page[T] envelope."""

import base64
import binascii

from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.core.schema import PulseSchema


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(cursor: str) -> str:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise PulseError(
            ErrorCode.VALIDATION_ERROR,
            "Invalid cursor.",
        ) from exc


class Page[T](PulseSchema):
    items: list[T]
    next_cursor: str | None = None
