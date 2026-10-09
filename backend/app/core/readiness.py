"""Dependency readiness, distinct from process liveness. No domain data is read."""

import asyncio
import os
import tempfile
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis


def _check_uploads() -> None:
    directory = Path(os.environ.get("PULSE_UPLOAD_DIR", "/data/uploads"))
    directory.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=directory) as probe:
        probe.write(b"ready")
        probe.flush()
        os.fsync(probe.fileno())


async def check(session: AsyncSession) -> bool:
    try:
        async with asyncio.timeout(3):
            await session.execute(text("SELECT 1"))
            await get_redis().ping()
            await asyncio.to_thread(_check_uploads)
        return True
    except Exception:
        # No dependency addresses, paths or credentials in the public response.
        return False
