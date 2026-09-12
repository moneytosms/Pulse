"""P3.9 (#43) notification-service test helpers.

Imported as top-level ``notifications_helpers`` (never
``tests.notifications_helpers``), matching ``helpers``/``records_helpers``
so mypy resolves one module name.

``insert_audit_event`` writes directly to ``audit_event`` with raw SQL —
P3.8 (real audit emission) hasn't landed, so there is no service call to
generate the rows the digest reads.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def insert_audit_event(
    app_database_url: str,
    *,
    patient_id: uuid.UUID,
    actor_role: str = "CLINICIAN",
    action: str = "ENTRY_VIEWED",
    outcome: str = "SUCCESS",
    occurred_at: datetime | None = None,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, actor_role, action, resource_type, patient_id, outcome, occurred_at) "
                    "VALUES (:id, :actor_role, :action, 'medical_entry', :patient_id, "
                    ":outcome, :occurred_at)"
                ),
                {
                    "id": event_id,
                    "actor_role": actor_role,
                    "action": action,
                    "patient_id": patient_id,
                    "outcome": outcome,
                    "occurred_at": occurred_at or datetime.now(UTC),
                },
            )
    finally:
        await engine.dispose()
    return event_id


async def wipe_audit_events(app_database_url: str) -> None:
    """`pulse_app` holds SELECT/INSERT only on `audit_event` (ADR-0008,
    append-only by GRANT) — a DELETE from the app role always raises
    `InsufficientPrivilegeError`, regardless of row count, since Postgres
    checks table privilege before matching rows. Test cleanup goes over
    the admin connection instead, same as `test_seed_entries.py`'s
    `_wipe_seed_marker` for the same reason. `app_database_url` is kept
    as a parameter only to trigger the `_environment` fixture that sets
    `ALEMBIC_DATABASE_URL`; it is not the URL used here."""
    engine = create_async_engine(os.environ["ALEMBIC_DATABASE_URL"])
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_event"))
    finally:
        await engine.dispose()


async def set_preference(
    app_database_url: str,
    *,
    user_id: uuid.UUID,
    notification_type: str,
    channel: str,
    enabled: bool,
) -> None:
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO notification_preference "
                    "(id, user_id, notification_type, channel, enabled) "
                    "VALUES (:id, :user_id, :notification_type, :channel, :enabled)"
                ),
                {
                    "id": uuid.uuid4(),
                    "user_id": user_id,
                    "notification_type": notification_type,
                    "channel": channel,
                    "enabled": enabled,
                },
            )
    finally:
        await engine.dispose()
