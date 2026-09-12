"""Test spine: real PostgreSQL + real Redis via testcontainers.

A mocked-database test tests the mock, and this project's risk is
entirely "did the filter actually apply to that query" (backend.md). So
the primary seam is `httpx.AsyncClient` over the real ASGI app, against
containers. The one injected double is `FakeIdentityProvider` — no SMTP.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

LoginFactory = Callable[..., Awaitable[Response]]

_BACKEND_DIR = Path(__file__).resolve().parents[1]
# Child-first: the app role has DML but not TRUNCATE on these (migration 0002),
# so teardown is ordered DELETEs, not a single TRUNCATE ... CASCADE.
_APP_TABLES = (
    "provider_staff",
    "patient_merge",
    "duplicate_review_item",
    "patient",
    '"user"',
    "provider",
)


@pytest.fixture(scope="session")
def _postgres() -> Iterator[PostgresContainer]:
    # Names match compose.yaml so migration 0001's hardcoded DATABASE/role
    # references resolve.
    with PostgresContainer(
        "postgres:18.6", username="pulse", password="pulse", dbname="pulse"
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def _redis() -> Iterator[RedisContainer]:
    with RedisContainer("redis:8.8.2") as rc:
        yield rc


@pytest.fixture(scope="session")
def _environment(_postgres: PostgresContainer, _redis: RedisContainer) -> Iterator[None]:
    host = _postgres.get_container_host_ip()
    port = _postgres.get_exposed_port(5432)
    admin_url = f"postgresql+asyncpg://pulse:pulse@{host}:{port}/pulse"
    app_url = f"postgresql+asyncpg://pulse_app:pulse_app@{host}:{port}/pulse"
    r_host = _redis.get_container_host_ip()
    r_port = _redis.get_exposed_port(6379)

    os.environ["ALEMBIC_DATABASE_URL"] = admin_url
    os.environ["DATABASE_URL"] = app_url
    os.environ["REDIS_URL"] = f"redis://{r_host}:{r_port}/0"

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def app_database_url(_environment: None) -> str:
    return os.environ["DATABASE_URL"]


@pytest_asyncio.fixture
async def db_engine(app_database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(app_database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    async with db_engine.begin() as conn:
        for table in _APP_TABLES:
            await conn.execute(text(f"DELETE FROM {table}"))


# Tests that touch neither the app nor the database — the enforcement lints and
# the route-coverage introspection — must not pay for a Postgres/Redis container.
# They are recognised by requesting none of the infra fixtures below.
_INFRA_FIXTURES = frozenset(
    {"client", "db_session", "db_engine", "register_and_login", "fake_idp"}
)


@pytest_asyncio.fixture(autouse=True)
async def _flush_redis(request: pytest.FixtureRequest) -> AsyncIterator[None]:
    if _INFRA_FIXTURES.isdisjoint(request.fixturenames):
        yield
        return

    request.getfixturevalue("_environment")
    from app.core.redis import close_redis, get_redis

    await close_redis()
    redis = get_redis()
    await redis.flushdb()
    yield
    await redis.flushdb()
    await close_redis()


@pytest_asyncio.fixture
async def fake_idp() -> object:
    from app.adapters.identity import FakeIdentityProvider

    return FakeIdentityProvider()


@pytest_asyncio.fixture
async def client(
    db_engine: AsyncEngine, fake_idp: object
) -> AsyncIterator[AsyncClient]:
    from app.db.session import get_session
    from app.main import app
    from app.modules.auth.dependencies import get_identity_provider

    maker = async_sessionmaker(db_engine, expire_on_commit=False)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_identity_provider] = lambda: fake_idp

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def register_and_login(
    client: AsyncClient, fake_idp: object
) -> LoginFactory:
    """Register -> verify (via the fake) -> login. Returns the login Response
    (its cookie jar is already on `client`).

    Idempotent on the email: a second call with an already-registered
    address just re-logs-in, so a multi-actor test can switch back to an
    earlier user by calling this again."""

    async def _make(
        *,
        email: str = "patient@example.com",
        password: str = "correct-horse-staple-9",
        role: str = "PATIENT",
        verify: bool = True,
    ) -> Response:
        reg = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "role": role},
        )
        if reg.status_code != 409:
            reg.raise_for_status()
            challenge_id, (token, _uid) = next(reversed(fake_idp.issued.items()))  # type: ignore[attr-defined]
            if verify:
                v = await client.post(
                    "/api/v1/auth/verify",
                    json={"challengeId": challenge_id, "token": token},
                )
                v.raise_for_status()
        login = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        login.raise_for_status()
        return login

    return _make
