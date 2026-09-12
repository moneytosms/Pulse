"""Notifications DI hooks — same shape as `records/dependencies.py`'s
`StorageProvider`. Other modules (consent's break-glass path) depend on
this to get a `NotificationProvider` without importing `app.adapters`
directly; cross-module import lint allows `app.modules.notifications.dependencies`.
"""

from app.adapters.notifications import MailpitNotificationProvider, NotificationProvider


def get_notification_provider() -> NotificationProvider:
    return MailpitNotificationProvider()
