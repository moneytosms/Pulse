import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# So `app.db.base` is importable regardless of cwd Alembic is run from.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.db.base import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations run as the admin role (compose.yaml's POSTGRES_USER), not the
# app runtime's `pulse_app` — that role doesn't exist until migration 0001
# creates it, so connecting as `pulse_app` by default here is a bootstrap
# deadlock. ALEMBIC_DATABASE_URL overrides for anything other than local
# compose; app.db.session's DATABASE_URL (pulse_app) is intentionally a
# separate setting and never used for migrations.
db_url = os.environ.get(
    "ALEMBIC_DATABASE_URL",
    "postgresql+asyncpg://pulse:pulse@postgres:5432/pulse",
)
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        future=True,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
