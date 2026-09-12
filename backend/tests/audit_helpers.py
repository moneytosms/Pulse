"""P3.8 (#45) audit-emission test helpers.

Imported as top-level ``audit_helpers`` (never ``tests.audit_helpers``),
matching ``helpers``/``records_helpers``/``notifications_helpers`` so
mypy resolves one module name.

Raw SQL against ``audit_event`` — the negative "no clinical value in
``metadata``" test needs to see the actual stored row, not just call the
service with a well-typed argument.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def fetch_events_for_patient(
    app_database_url: str, patient_id: uuid.UUID
) -> list[dict[str, Any]]:
    engine = create_async_engine(app_database_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, actor_user_id, actor_role, action, resource_type, "
                        "resource_id, patient_id, outcome, request_id, metadata "
                        "FROM audit_event WHERE patient_id = :patient_id "
                        "ORDER BY occurred_at ASC"
                    ),
                    {"patient_id": patient_id},
                )
            ).mappings().all()
            result = []
            for row in rows:
                d = dict(row)
                if isinstance(d["metadata"], str):  # asyncpg jsonb, undecoded
                    d["metadata"] = json.loads(d["metadata"])
                result.append(d)
            return result
    finally:
        await engine.dispose()


async def seed_event_for_patient(
    app_database_url: str,
    *,
    patient_id: uuid.UUID,
    actor_role: str = "CLINICIAN",
    action: str = "ENTRY_VIEWED",
    outcome: str = "SUCCESS",
    occurred_at: datetime | None = None,
    metadata: dict[str, object] | None = None,
) -> uuid.UUID:
    """A raw ``audit_event`` row for a patient the signed-in caller does
    *not* own — for the "another patient's events never leak" test, where
    a real access-gated read could never have produced the row in the
    first place."""
    event_id = uuid.uuid4()
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO audit_event "
                    "(id, actor_role, action, resource_type, patient_id, outcome, "
                    " occurred_at, metadata) "
                    "VALUES (:id, :actor_role, :action, 'medical_entry', :patient_id, "
                    ":outcome, :occurred_at, :metadata)"
                ),
                {
                    "id": event_id,
                    "actor_role": actor_role,
                    "action": action,
                    "patient_id": patient_id,
                    "outcome": outcome,
                    "occurred_at": occurred_at or datetime.now(UTC),
                    "metadata": json.dumps(metadata or {}),
                },
            )
    finally:
        await engine.dispose()
    return event_id


async def insert_bare_patient(
    app_database_url: str, *, full_name: str = "Other Patient"
) -> uuid.UUID:
    """An unclaimed Patient (`user_id` NULL — clinical-safety.md: load-
    bearing, not a bug) with no relationship to any signed-in caller.
    `audit_event.patient_id` is a real FK, so "another patient" in a test
    needs a real row, not just a random UUID."""
    patient_id = uuid.uuid4()
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO patient (id, full_name) VALUES (:id, :full_name)"),
                {"id": patient_id, "full_name": full_name},
            )
    finally:
        await engine.dispose()
    return patient_id


async def wipe_audit_events(app_database_url: str) -> None:
    """`pulse_app` holds only SELECT/INSERT on `audit_event` (ADR-0008,
    append-only by `GRANT`) — a `DELETE` under `app_database_url` is a
    permission error, not a no-op. Test cleanup runs as the admin role
    instead; `app_database_url` stays a parameter only so call sites match
    every other `wipe_*` helper's signature."""
    del app_database_url
    admin_url = os.environ["ALEMBIC_DATABASE_URL"]
    engine = create_async_engine(admin_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_event"))
    finally:
        await engine.dispose()
