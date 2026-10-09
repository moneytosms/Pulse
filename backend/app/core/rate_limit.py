"""Atomic, expiring Redis counters for expensive and security-sensitive actions."""

import hashlib

from redis.asyncio import Redis

from app.core.errors import ErrorCode
from app.core.exceptions import PulseError

_COUNTER = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


async def check_limit(redis: Redis, scope: str, subject: str, limit: int, window: int) -> None:
    # Identifiers never appear in Redis keys or error messages.
    key = f"rate:{scope}:{hashlib.sha256(subject.encode()).hexdigest()}"
    count = await redis.eval(_COUNTER, 1, key, window)
    if int(count) > limit:
        raise PulseError(ErrorCode.RATE_LIMITED, "Try again later.", http_status=429)
