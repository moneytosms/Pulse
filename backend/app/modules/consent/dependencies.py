"""Consent DI hooks.

`get_notification_provider` mirrors `records/dependencies.py`'s
`get_storage_provider` — overridden with `FakeNotificationProvider` in
tests so break-glass/revoke's mandatory delivery never touches real SMTP.
"""

from app.adapters.notifications import MailpitNotificationProvider, NotificationProvider


def get_notification_provider() -> NotificationProvider:
    return MailpitNotificationProvider()
