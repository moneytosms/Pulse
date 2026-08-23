"""Async engine + session factory.

`DATABASE_URL` defaults to the value compose.yaml sets for the backend
service (app role `pulse_app`, database `pulse`), so this works
unconfigured inside the compose network and only needs overriding for
local/CI runs outside it.
"""

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://pulse_app:pulse_app@postgres:5432/pulse",
)

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with async_session() as session:
        yield session
