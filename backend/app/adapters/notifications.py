"""NotificationProvider interface. Declared in Phase 1; implemented in Phase 3
(P3.9, #43).

A notification stores `type` + `params`, never rendered text, and params
carry no clinical data (clinical-safety.md).
"""

import asyncio
import os
import smtplib
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any


class NotificationProvider(ABC):
    @abstractmethod
    async def send(self, channel: str, address: str, type_: str, params: dict[str, Any]) -> None:
        ...


class FakeNotificationProvider(NotificationProvider):
    """In-memory, no SMTP. Tests read the captured sends off `.sent`."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict[str, Any]]] = []

    async def send(self, channel: str, address: str, type_: str, params: dict[str, Any]) -> None:
        self.sent.append((channel, address, type_, params))


class MailpitNotificationProvider(NotificationProvider):
    """EMAIL over Mailpit SMTP, same shape as `MailpitIdentityProvider`. No
    SMS provider exists anywhere in this stack yet, so other channels are a
    no-op rather than a failure."""

    def __init__(self) -> None:
        self._smtp_host = os.environ.get("SMTP_HOST", "mailpit")
        self._smtp_port = int(os.environ.get("SMTP_PORT", "1025"))
        self._from = os.environ.get("MAIL_FROM", "no-reply@pulse.local")

    async def send(self, channel: str, address: str, type_: str, params: dict[str, Any]) -> None:
        if channel != "EMAIL":
            return
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = address
        msg["Subject"] = f"Pulse notification: {type_}"
        msg.set_content(f"{type_}: {params}")
        await asyncio.to_thread(self._smtp_send, msg)

    def _smtp_send(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=10) as smtp:
            smtp.send_message(msg)
