"""IdentityProvider: email verification as two round trips.

`start_verification` then `complete_verification` — two calls because
verification is two round trips and ABHA's flow needs somewhere to go
(backend.md). SMTP defaults to Mailpit locally and supports authenticated
delivery for hosted deployments; tests use an in-memory fake.
"""

import asyncio
import os
from abc import ABC, abstractmethod
from email.message import EmailMessage
from enum import StrEnum
from uuid import UUID

from redis.asyncio import Redis

from app.adapters.smtp import SMTPSettings, send_message, sender_address
from app.core.security import new_token, token_hash

CHALLENGE_TTL_SECONDS = 24 * 3600
_TOMBSTONE_TTL_SECONDS = 72 * 3600
_CHALLENGE_KEY = "verif:{}"
_TOMBSTONE_KEY = "verif_seen:{}"


class VerificationOutcome(StrEnum):
    OK = "OK"
    INVALID = "INVALID"
    EXPIRED = "EXPIRED"


class IdentityProvider(ABC):
    @abstractmethod
    async def start_verification(self, user_id: UUID, email: str, locale: str) -> str:
        """Issue a challenge, deliver its token out of band, return the challenge id."""

    @abstractmethod
    async def complete_verification(
        self, challenge_id: str, token: str
    ) -> tuple[VerificationOutcome, UUID | None]:
        """Redeem a challenge. Returns the verified user id only on OK."""


class FakeIdentityProvider(IdentityProvider):
    """In-memory, no SMTP. Tests read the captured token off `.issued`."""

    def __init__(self) -> None:
        # challenge_id -> (token, user_id); consumed challenges move to _spent.
        self.issued: dict[str, tuple[str, UUID]] = {}
        self._spent: set[str] = set()

    async def start_verification(self, user_id: UUID, email: str, locale: str) -> str:
        challenge_id = new_token()
        token = new_token()
        self.issued[challenge_id] = (token, user_id)
        return challenge_id

    async def complete_verification(
        self, challenge_id: str, token: str
    ) -> tuple[VerificationOutcome, UUID | None]:
        if challenge_id not in self.issued:
            outcome = (
                VerificationOutcome.EXPIRED
                if challenge_id in self._spent
                else VerificationOutcome.INVALID
            )
            return outcome, None
        real_token, user_id = self.issued[challenge_id]
        if token != real_token:
            return VerificationOutcome.INVALID, None
        del self.issued[challenge_id]
        self._spent.add(challenge_id)
        return VerificationOutcome.OK, user_id

    def token_for(self, challenge_id: str) -> str:
        return self.issued[challenge_id][0]


class SmtpIdentityProvider(IdentityProvider):
    """Challenges in Redis (TTL'd); token delivered as an email link via SMTP."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._smtp = SMTPSettings.from_env()
        self._base_url = os.environ.get("PUBLIC_BASE_URL", "http://localhost").rstrip("/")
        self._from = sender_address(username=self._smtp.username)

    async def start_verification(self, user_id: UUID, email: str, locale: str) -> str:
        challenge_id = new_token()
        token = new_token()
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                _CHALLENGE_KEY.format(challenge_id),
                mapping={"userId": str(user_id), "tokenHash": token_hash(token)},
            )
            pipe.expire(_CHALLENGE_KEY.format(challenge_id), CHALLENGE_TTL_SECONDS)
            pipe.set(_TOMBSTONE_KEY.format(challenge_id), "1", ex=_TOMBSTONE_TTL_SECONDS)
            await pipe.execute()
        await self._send_email(email, locale, challenge_id, token)
        return challenge_id

    async def complete_verification(
        self, challenge_id: str, token: str
    ) -> tuple[VerificationOutcome, UUID | None]:
        data = await self._redis.hgetall(_CHALLENGE_KEY.format(challenge_id))
        if not data:
            seen = await self._redis.exists(_TOMBSTONE_KEY.format(challenge_id))
            return (VerificationOutcome.EXPIRED if seen else VerificationOutcome.INVALID), None
        if token_hash(token) != data["tokenHash"]:
            return VerificationOutcome.INVALID, None
        await self._redis.delete(_CHALLENGE_KEY.format(challenge_id))
        return VerificationOutcome.OK, UUID(str(data["userId"]))

    async def _send_email(self, email: str, locale: str, challenge_id: str, token: str) -> None:
        link = f"{self._base_url}/{locale}/verify?challenge={challenge_id}&token={token}"
        msg = EmailMessage()
        msg["From"] = self._from
        msg["To"] = email
        msg["Subject"] = "Verify your Pulse account"
        msg.set_content(f"Confirm your email address:\n\n{link}\n")
        await asyncio.to_thread(self._smtp_send, msg)

    def _smtp_send(self, msg: EmailMessage) -> None:
        send_message(msg, self._smtp)
