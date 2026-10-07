"""SMTP configuration and encrypted authenticated delivery."""

from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.smtp import SMTPSettings, send_message, sender_address


def test_defaults_keep_mailpit_usable_without_credentials() -> None:
    settings = SMTPSettings.from_env({})

    assert settings.host == "mailpit"
    assert settings.port == 1025
    assert settings.username is None
    assert settings.password is None
    assert not settings.starttls
    assert not settings.use_ssl


def test_authenticated_settings_require_encryption() -> None:
    with pytest.raises(ValueError, match="requires STARTTLS or SSL"):
        SMTPSettings.from_env(
            {
                "SMTP_HOST": "smtp.gmail.com",
                "SMTP_PORT": "587",
                "SMTP_USERNAME": "sender@example.com",
                "SMTP_PASSWORD": "app-password",
            }
        )


def test_authenticated_settings_require_both_credentials() -> None:
    with pytest.raises(ValueError, match="SMTP_PASSWORD is required"):
        SMTPSettings.from_env(
            {
                "SMTP_USERNAME": "sender@example.com",
                "SMTP_STARTTLS": "true",
            }
        )


def test_gmail_delivery_starts_tls_then_authenticates_and_sends() -> None:
    settings = SMTPSettings(
        host="smtp.gmail.com",
        port=587,
        username="sender@example.com",
        password="app-password",
        starttls=True,
    )
    message = EmailMessage()
    message["From"] = "sender@example.com"
    message["To"] = "recipient@example.com"
    message.set_content("Verify this account")
    smtp = MagicMock()

    with patch("app.adapters.smtp.smtplib.SMTP") as smtp_factory:
        smtp_factory.return_value.__enter__.return_value = smtp
        send_message(message, settings)

    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("sender@example.com", "app-password")
    smtp.send_message.assert_called_once_with(message)


def test_sender_defaults_to_authenticated_account() -> None:
    assert sender_address({}, username="sender@example.com") == "sender@example.com"
