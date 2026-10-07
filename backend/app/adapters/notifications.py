"""NotificationProvider interface. Declared in Phase 1; implemented in Phase 3
(P3.9, #43).

A notification stores `type` + `params`, never rendered text, and params
carry no clinical data (clinical-safety.md).
"""

import asyncio
from abc import ABC, abstractmethod
from email.message import EmailMessage
from typing import Any

from app.adapters.smtp import SMTPSettings, send_message, sender_address


class NotificationProvider(ABC):
    @abstractmethod
    async def send(
        self, channel: str, address: str, type_: str, params: dict[str, Any]
    ) -> None: ...


class FakeNotificationProvider(NotificationProvider):
    """In-memory, no SMTP. Tests read the captured sends off `.sent`."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict[str, Any]]] = []

    async def send(self, channel: str, address: str, type_: str, params: dict[str, Any]) -> None:
        self.sent.append((channel, address, type_, params))


class SmtpNotificationProvider(NotificationProvider):
    """EMAIL over configured SMTP, same shape as `SmtpIdentityProvider`. No
    SMS provider exists anywhere in this stack yet, so other channels are a
    no-op rather than a failure."""

    def __init__(self) -> None:
        self._smtp = SMTPSettings.from_env()
        self._from = sender_address(username=self._smtp.username)

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
        send_message(msg, self._smtp)
