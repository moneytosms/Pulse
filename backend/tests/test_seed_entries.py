"""P2.4 — seed part 2: Medical Entries loaded for the seeded Patients.

ASGI-client seam. Runs the real ``run_seed`` loader (identity + clinical)
against the test containers, then asserts over HTTP that the timeline is
non-empty and that both required lab-value shapes made it in. Cleans up
via ``rh.wipe_records`` / ``wipe_identity`` like the other Phase 2 tests,
plus the ``seed_marker`` row so each test gets its own unskipped run --
the app role holds SELECT/INSERT only on it (migration 0003), so that
delete goes over the admin connection, same as Alembic's.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest_asyncio
import records_helpers as rh
from helpers import wipe_identity
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_STAFF_EMAIL = "staff000@example.com"
_DEV_PASSWORD = "Pulse@demo1"
# staff000 is the only seeded Provider Staff user with a known (demo) password
# -- everyone else gets an unusable hash (`_build_objects`). Phase 3 rule 2
# (`accessible_entries`) narrows a Provider Staff read to entries authored by
# their OWN Provider, so every lookup here must stay scoped to staff000's
# Provider (Aster Medcity, per `seed/data/identity/provider_staff.csv`).
_STAFF_PROVIDER_ID = "2908b677-91c9-5a6e-b5c5-6db5a46f60b0"


async def _wipe_seed_marker() -> None:
    admin_url = os.environ["ALEMBIC_DATABASE_URL"]
    engine = create_async_engine(admin_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM seed_marker"))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)
    await _wipe_seed_marker()


@pytest_asyncio.fixture(autouse=True)
async def _seed_loader_engine(app_database_url: str) -> AsyncIterator[None]:
    """`run_seed` calls the `async_session` it imported from
    `app.db.session` at module-import time. In the full suite that import
    can happen at collection (e.g. `test_route_coverage.py` imports
    `app.main` at module scope), before this file's `_environment` fixture
    ever sets `DATABASE_URL` -- so that binding is stuck on the compose
    hostname, not the test container. Point `app.db.seed_loader`'s own
    reference at a session factory bound to the real test database for the
    duration of this test, matching seed/tests/test_loader.py's per-test
    engine (that suite avoids the problem by importing after the env is
    set; this one can't assume it runs first)."""
    import app.db.seed_loader as seed_loader

    engine = create_async_engine(app_database_url)
    original = seed_loader.async_session  # type: ignore[attr-defined]
    seed_loader.async_session = async_sessionmaker(  # type: ignore[attr-defined]
        engine, expire_on_commit=False
    )
    yield
    seed_loader.async_session = original  # type: ignore[attr-defined]
    await engine.dispose()


async def _run_seed() -> None:
    from app.db.seed_loader import run_seed

    result = await run_seed()
    assert result.skipped is False


async def _lab_report_matching(app_database_url: str, where: str) -> tuple[str, str]:
    """(entry_id, patient_id) of one lab_report row matching `where`."""
    engine = create_async_engine(app_database_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT medical_entry.id, medical_entry.patient_id "
                        "FROM lab_report JOIN medical_entry "
                        "ON lab_report.id = medical_entry.id "
                        f"WHERE {where} LIMIT 1"
                    )
                )
            ).first()
            assert row is not None, f"no lab_report row matches: {where}"
            return str(row[0]), str(row[1])
    finally:
        await engine.dispose()


async def test_seed_loads_entries_for_a_seeded_patient(
    client: AsyncClient, app_database_url: str
) -> None:
    await _run_seed()

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": _STAFF_EMAIL, "password": _DEV_PASSWORD},
    )
    login.raise_for_status()

    _, patient_id = await _lab_report_matching(
        app_database_url, f"medical_entry.source_provider_id = '{_STAFF_PROVIDER_ID}'"
    )
    resp = await client.get(f"/api/v1/patients/{patient_id}/entries")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) > 0


async def test_seed_includes_an_out_of_range_numeric_lab(
    client: AsyncClient, app_database_url: str
) -> None:
    await _run_seed()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": _STAFF_EMAIL, "password": _DEV_PASSWORD},
    )
    login.raise_for_status()

    entry_id, _ = await _lab_report_matching(
        app_database_url,
        "value_numeric IS NOT NULL AND reference_low IS NOT NULL "
        "AND (value_numeric < reference_low OR value_numeric > reference_high) "
        f"AND medical_entry.source_provider_id = '{_STAFF_PROVIDER_ID}'",
    )

    resp = await client.get(f"/api/v1/entries/{entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entryType"] == "LAB_REPORT"
    value = Decimal(str(body["valueNumeric"]))
    assert value < Decimal(str(body["referenceLow"])) or value > Decimal(
        str(body["referenceHigh"])
    )


async def test_seed_includes_a_text_valued_lab(
    client: AsyncClient, app_database_url: str
) -> None:
    await _run_seed()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": _STAFF_EMAIL, "password": _DEV_PASSWORD},
    )
    login.raise_for_status()

    entry_id, _ = await _lab_report_matching(
        app_database_url,
        "value_text IS NOT NULL AND value_numeric IS NULL "
        f"AND medical_entry.source_provider_id = '{_STAFF_PROVIDER_ID}'",
    )

    resp = await client.get(f"/api/v1/entries/{entry_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["entryType"] == "LAB_REPORT"
    assert body["valueText"] is not None
    assert body["valueNumeric"] is None


async def test_second_seed_run_is_a_noop(client: AsyncClient, app_database_url: str) -> None:
    from app.db.seed_loader import run_seed

    await _run_seed()

    async def _entry_count() -> int:
        engine = create_async_engine(app_database_url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT count(*) FROM medical_entry"))
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    before = await _entry_count()
    result = await run_seed()
    assert result.skipped is True
    assert await _entry_count() == before
