"""Shared SMTP configuration and delivery for mail adapters.

Local Compose defaults to Mailpit without authentication. Gmail and other
authenticated SMTP servers use environment-provided credentials and an
encrypted connection.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from email.message import EmailMessage


def _env_flag(value: str | None, *, name: str, default: bool = False) -> bool:
    if value is None:
        return default
    normalised = value.strip().lower()
    if normalised in {"1", "true", "yes", "on"}:
        return True
    if normalised in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str | None = None
    password: str | None = None
    starttls: bool = False
    use_ssl: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> SMTPSettings:
        source = os.environ if environ is None else environ
        host = source.get("SMTP_HOST", "mailpit").strip()
        if not host:
            raise ValueError("SMTP_HOST must not be empty.")

        port = int(source.get("SMTP_PORT", "1025"))
        if not 1 <= port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535.")

        username = source.get("SMTP_USERNAME", "").strip() or None
        password = source.get("SMTP_PASSWORD", "").strip() or None
        starttls = _env_flag(source.get("SMTP_STARTTLS"), name="SMTP_STARTTLS")
        use_ssl = _env_flag(source.get("SMTP_SSL"), name="SMTP_SSL")

        if username is not None and password is None:
            raise ValueError("SMTP_PASSWORD is required when SMTP_USERNAME is set.")
        if password is not None and username is None:
            raise ValueError("SMTP_USERNAME is required when SMTP_PASSWORD is set.")
        if starttls and use_ssl:
            raise ValueError("SMTP_STARTTLS and SMTP_SSL cannot both be enabled.")
        if username is not None and not (starttls or use_ssl):
            raise ValueError("SMTP authentication requires STARTTLS or SSL.")

        return cls(
            host=host,
            port=port,
            username=username,
            password=password,
            starttls=starttls,
            use_ssl=use_ssl,
        )


def sender_address(environ: Mapping[str, str] | None = None, *, username: str | None = None) -> str:
    source = os.environ if environ is None else environ
    return source.get("MAIL_FROM", "").strip() or username or "no-reply@pulse.local"


def send_message(message: EmailMessage, settings: SMTPSettings) -> None:
    """Send a message, applying configured TLS and authentication."""
    context = ssl.create_default_context()

    if settings.use_ssl:
        with smtplib.SMTP_SSL(
            settings.host,
            settings.port,
            timeout=10,
            context=context,
        ) as smtp:
            _authenticate(smtp, settings)
            smtp.send_message(message)
        return

    with smtplib.SMTP(settings.host, settings.port, timeout=10) as smtp:
        if settings.starttls:
            smtp.starttls(context=context)
        _authenticate(smtp, settings)
        smtp.send_message(message)


def _authenticate(smtp: smtplib.SMTP, settings: SMTPSettings) -> None:
    if settings.username is not None and settings.password is not None:
        smtp.login(settings.username, settings.password)
