"""Notification wire contract (P3.9, #43).

The Patient's notification digest and their delivery preferences. Never
clinical content — a notification is a copy of information sitting outside
the consent filter (clinical-safety.md). `title`/`body` are an English
default rendered by the service from `type` + `params` at read time (same
shape as the stub); the stored row itself never holds rendered text.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import ConfigDict, Field, StrictInt

from app.core.schema import PulseSchema


class NotificationType(StrEnum):
    CONSENT_GRANTED = "CONSENT_GRANTED"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    RECORD_UPLOADED = "RECORD_UPLOADED"
    # Emergency access to a Patient's record (P3.9, #43). Mandatory — see
    # `app.modules.notifications.service.MANDATORY_TYPES`.
    BREAK_GLASS_ACCESS = "BREAK_GLASS_ACCESS"
    # "A clinician viewed your records" — read-computed digest, never a
    # per-view notification (domain-model.md, "Notifications").
    DAILY_DIGEST = "DAILY_DIGEST"


class NotificationChannel(StrEnum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"


class NotificationParams(PulseSchema):
    """Only counts and typed identifiers can leave the consent filter."""

    model_config = ConfigDict(extra="forbid")
    view_count: StrictInt | None = Field(default=None, ge=0)
    entry_id: UUID | None = None
    patient_id: UUID | None = None
    consent_id: UUID | None = None
    provider_id: UUID | None = None


class Notification(PulseSchema):
    id: UUID
    type: NotificationType
    title: str
    body: str
    params: NotificationParams = Field(default_factory=NotificationParams)
    read_at: datetime | None = None
    created_at: datetime


class NotificationPreference(PulseSchema):
    notification_type: NotificationType
    channel: NotificationChannel
    enabled: bool
