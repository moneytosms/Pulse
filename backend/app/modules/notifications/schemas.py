"""Notification wire contract — PROVISIONAL (finalised in Phase 3, P3.9).

The Patient's notification digest and their delivery preferences. Never
clinical content — a notification is a copy of information sitting outside
the consent filter (clinical-safety.md).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from app.core.schema import PulseSchema


class NotificationType(StrEnum):
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    RECORD_UPLOADED = "RECORD_UPLOADED"


class NotificationChannel(StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"


class Notification(PulseSchema):
    id: UUID
    type: NotificationType
    title: str
    body: str
    read_at: datetime | None = None
    created_at: datetime


class NotificationPreference(PulseSchema):
    notification_type: NotificationType
    channel: NotificationChannel
    enabled: bool
