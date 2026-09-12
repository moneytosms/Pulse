"""P3.9 (#43) — `notify()`: mandatory-type gating, preference gating, and
immediate delivery scheduling.

Direct service seam against real Postgres (`db_session`) — `notify()` has
no HTTP entry point of its own in this PR (it will be called from
consent/break-glass services in a later one), and this is genuinely
branchy logic worth a unit-shaped test (backend.md). No mocked database:
preferences are real rows.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

import notifications_helpers as nh
import pytest_asyncio
from helpers import wipe_identity
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.notifications import FakeNotificationProvider
from app.core.actor import Actor
from app.core.authz import Role
from app.core.errors import ErrorCode
from app.core.exceptions import PulseError
from app.modules.notifications import repository, service
from app.modules.notifications.models import Notification as NotificationRow
from app.modules.notifications.schemas import NotificationChannel, NotificationType
from app.modules.users.models import Patient, User


class _FakeScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, tuple[Any, ...], dict[str, Any]]] = []

    def add_task(self, func: Any, /, *args: Any, **kwargs: Any) -> None:
        self.calls.append((func, args, kwargs))


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await wipe_identity(app_database_url)


async def _rows_for(db_session: AsyncSession, user_id: uuid.UUID) -> list[NotificationRow]:
    result = await db_session.execute(
        select(NotificationRow).where(NotificationRow.user_id == user_id)
    )
    return list(result.scalars().all())


async def _make_patient_user(db_session: AsyncSession, email: str) -> uuid.UUID:
    user = User(email=email, password_hash="x", role=Role.PATIENT)
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user.id


async def test_notify_inserts_a_row_for_an_optional_type_with_no_preference_set(
    db_session: AsyncSession,
) -> None:
    user_id = await _make_patient_user(db_session, "notify-default@example.com")
    result = await service.notify(
        db_session, user_id, NotificationType.RECORD_UPLOADED, {"entryId": "e1"}
    )
    assert result is not None
    rows = await _rows_for(db_session, user_id)
    assert len(rows) == 1


async def test_notify_is_suppressed_when_the_in_app_preference_is_disabled(
    db_session: AsyncSession, app_database_url: str
) -> None:
    user_id = await _make_patient_user(db_session, "notify-disabled@example.com")
    await nh.set_preference(
        app_database_url,
        user_id=user_id,
        notification_type="RECORD_UPLOADED",
        channel="IN_APP",
        enabled=False,
    )
    result = await service.notify(
        db_session, user_id, NotificationType.RECORD_UPLOADED, {"entryId": "e1"}
    )
    assert result is None
    rows = await _rows_for(db_session, user_id)
    assert rows == []


async def test_notify_ignores_a_disabled_preference_for_a_mandatory_type(
    db_session: AsyncSession, app_database_url: str
) -> None:
    user_id = await _make_patient_user(db_session, "notify-mandatory@example.com")
    # A row here should be impossible through the API (test_notification_preferences.py
    # covers that), but the service must not trust it even if one exists.
    await nh.set_preference(
        app_database_url,
        user_id=user_id,
        notification_type="CONSENT_REVOKED",
        channel="IN_APP",
        enabled=False,
    )
    result = await service.notify(
        db_session, user_id, NotificationType.CONSENT_REVOKED, {"consentId": "c1"}
    )
    assert result is not None


async def test_notify_schedules_provider_send_for_a_mandatory_type(
    db_session: AsyncSession,
) -> None:
    user_id = await _make_patient_user(db_session, "notify-mandatory-send@example.com")
    provider = FakeNotificationProvider()
    scheduler = _FakeScheduler()
    await service.notify(
        db_session,
        user_id,
        NotificationType.BREAK_GLASS_ACCESS,
        {"providerId": "p1"},
        provider=provider,
        background_tasks=scheduler,
    )
    assert len(scheduler.calls) == 1
    func, args, _ = scheduler.calls[0]
    # Bound methods compare equal by (__self__, __func__) even when `is`
    # differs — accessing `provider.send` twice yields distinct objects.
    assert func == provider.send
    assert args[0] == NotificationChannel.EMAIL.value
    assert args[1] == "notify-mandatory-send@example.com"
    assert args[2] == NotificationType.BREAK_GLASS_ACCESS.value


async def test_notify_does_not_schedule_provider_send_for_an_optional_type(
    db_session: AsyncSession,
) -> None:
    user_id = await _make_patient_user(db_session, "notify-optional-no-send@example.com")
    provider = FakeNotificationProvider()
    scheduler = _FakeScheduler()
    await service.notify(
        db_session,
        user_id,
        NotificationType.RECORD_UPLOADED,
        {"entryId": "e1"},
        provider=provider,
        background_tasks=scheduler,
    )
    assert scheduler.calls == []


async def test_mark_read_sets_read_at(db_session: AsyncSession) -> None:
    user_id = await _make_patient_user(db_session, "mark-read@example.com")
    actor = Actor(user_id=user_id, role=Role.PATIENT)
    created = await service.notify(
        db_session, user_id, NotificationType.RECORD_UPLOADED, {"entryId": "e1"}
    )
    assert created is not None
    updated = await service.mark_read(db_session, actor, created.id)
    assert updated.read_at is not None


async def test_mark_read_is_idempotent(db_session: AsyncSession) -> None:
    user_id = await _make_patient_user(db_session, "mark-read-twice@example.com")
    actor = Actor(user_id=user_id, role=Role.PATIENT)
    created = await service.notify(
        db_session, user_id, NotificationType.RECORD_UPLOADED, {"entryId": "e1"}
    )
    assert created is not None
    first = await service.mark_read(db_session, actor, created.id)
    second = await service.mark_read(db_session, actor, created.id)
    assert first.read_at == second.read_at


async def test_mark_read_on_someone_elses_notification_is_not_found(
    db_session: AsyncSession,
) -> None:
    owner_id = await _make_patient_user(db_session, "mark-read-owner@example.com")
    other_id = await _make_patient_user(db_session, "mark-read-other@example.com")
    other_actor = Actor(user_id=other_id, role=Role.PATIENT)
    created = await service.notify(
        db_session, owner_id, NotificationType.RECORD_UPLOADED, {"entryId": "e1"}
    )
    assert created is not None
    try:
        await service.mark_read(db_session, other_actor, created.id)
        raise AssertionError("expected PulseError")
    except PulseError as exc:
        assert exc.code == ErrorCode.NOT_FOUND


async def test_a_view_does_not_by_itself_create_any_notification(
    db_session: AsyncSession, app_database_url: str
) -> None:
    """No ORM hook, no listener — inserting an ENTRY_VIEWED audit row must
    not, on its own, create a notification. Only a later read of the
    notification list computes the digest."""
    user_id = await _make_patient_user(db_session, "no-per-view@example.com")
    patient = Patient(user_id=user_id, full_name="No Per View")
    db_session.add(patient)
    await db_session.commit()

    await nh.insert_audit_event(app_database_url, patient_id=patient.id)

    rows = await repository.list_notifications(db_session, user_id)
    assert rows == ([], None)
