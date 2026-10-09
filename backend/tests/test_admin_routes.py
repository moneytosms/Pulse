"""P4.3 (#54) — admin HTTP surface. ASGI-client seam, real Postgres/Redis.

Negative test first (backend.md): a non-Administrator gets 403 from every
admin route. Then: an Administrator's response never carries clinical
content, on any of them (ADR-0007) — the queue is built from patients and
entries inserted directly against the database, bypassing the API, so the
clinical text is only ever readable through the response under test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest_asyncio
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_PW = "correct-horse-staple-9"
_CLINICAL_TEXT = "Type 2 diabetes mellitus"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str):  # type: ignore[no-untyped-def]
    yield
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            for table in ("diagnosis", "medical_entry", "duplicate_review_item", "patient_merge"):
                await conn.execute(text(f"DELETE FROM {table}"))
    finally:
        await engine.dispose()
    await wipe_identity(app_database_url)


async def _insert_duplicate_pair_with_entry(app_database_url: str) -> None:
    engine = create_async_engine(app_database_url)
    try:
        async with engine.begin() as conn:
            a_id, b_id, entry_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
            await conn.execute(
                text(
                    "INSERT INTO patient (id, full_name, date_of_birth, phone) "
                    "VALUES (:id, 'Ramesh Menon', '1980-01-01', '+91 90000 00010')"
                ),
                {"id": a_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO patient (id, full_name, date_of_birth, phone) "
                    "VALUES (:id, 'Menon Ramesh', '1980-01-01', '+91 90000 00010')"
                ),
                {"id": b_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO duplicate_review_item "
                    "(id, patient_id_a, patient_id_b, score, status) "
                    "VALUES (:id, :a, :b, 0.9, 'PENDING')"
                ),
                {"id": uuid.uuid4(), "a": min(a_id, b_id, key=str), "b": max(a_id, b_id, key=str)},
            )
            await conn.execute(
                text(
                    "INSERT INTO medical_entry "
                    "(id, patient_id, entry_type, occurred_at, recorded_at, is_critical, metadata) "
                    "VALUES (:id, :pid, 'DIAGNOSIS', :occurred, :occurred, false, '{}')"
                ),
                {"id": entry_id, "pid": a_id, "occurred": datetime(2020, 1, 1, tzinfo=UTC)},
            )
            await conn.execute(
                text(
                    "INSERT INTO diagnosis (id, code_system, code, display_name) "
                    "VALUES (:id, 'SNOMED-CT', '44054006', :display)"
                ),
                {"id": entry_id, "display": _CLINICAL_TEXT},
            )
    finally:
        await engine.dispose()


async def test_non_administrator_forbidden_on_every_admin_route(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="patient-admin-routes@example.com", role="PATIENT")

    get_resp = await client.get("/api/v1/admin/duplicate-review")
    assert get_resp.status_code == 403

    post_resp = await client.post(
        "/api/v1/admin/duplicate-review/not-duplicate",
        json={"patientIdA": str(uuid.uuid4()), "patientIdB": str(uuid.uuid4())},
    )
    assert post_resp.status_code == 403

    merge_resp = await client.post(
        "/api/v1/admin/duplicate-review/merge",
        json={"winnerPatientId": str(uuid.uuid4()), "loserPatientId": str(uuid.uuid4())},
    )
    assert merge_resp.status_code == 403

    reverse_resp = await client.post(f"/api/v1/admin/merges/{uuid.uuid4()}/reverse")
    assert reverse_resp.status_code == 403

    merges_resp = await client.get("/api/v1/admin/merges")
    assert merges_resp.status_code == 403


async def test_administrator_duplicate_review_queue_carries_no_clinical_content(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await _insert_duplicate_pair_with_entry(app_database_url)
    await register_and_login(email="admin-routes@example.com", role="ADMINISTRATOR")

    resp = await client.get("/api/v1/admin/duplicate-review")
    assert resp.status_code == 200
    body = resp.json()["items"]
    assert len(body) == 1
    item = body[0]
    assert set(item.keys()) == {"id", "patientA", "patientB", "score", "status"}
    for side in (item["patientA"], item["patientB"]):
        assert set(side.keys()) == {
            "id",
            "fullName",
            "dateOfBirth",
            "phone",
            "claimed",
            "entryCount",
        }
    assert {item["patientA"]["entryCount"], item["patientB"]["entryCount"]} == {1, 0}
    assert _CLINICAL_TEXT not in resp.text
    assert "44054006" not in resp.text


async def test_reversible_merges_list_survives_sessions_and_drops_reversed(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await _insert_duplicate_pair_with_entry(app_database_url)
    await register_and_login(email="admin-merges@example.com", role="ADMINISTRATOR")
    pair = (await client.get("/api/v1/admin/duplicate-review")).json()["items"][0]
    winner, loser = pair["patientA"], pair["patientB"]
    merged = await client.post(
        "/api/v1/admin/duplicate-review/merge",
        json={"winnerPatientId": winner["id"], "loserPatientId": loser["id"]},
    )
    assert merged.status_code == 201

    # A fresh session has no in-memory merge id; the list must supply it.
    client.cookies.clear()
    await register_and_login(email="admin-merges@example.com", role="ADMINISTRATOR")
    resp = await client.get("/api/v1/admin/merges")
    assert resp.status_code == 200
    [row] = resp.json()["items"]
    assert row["id"] == merged.json()["id"]
    assert row["winnerName"] == winner["fullName"]
    assert row["loserName"] == loser["fullName"]
    assert _CLINICAL_TEXT not in resp.text

    reversed_resp = await client.post(f"/api/v1/admin/merges/{row['id']}/reverse")
    assert reversed_resp.status_code == 200
    assert (await client.get("/api/v1/admin/merges")).json()["items"] == []


async def test_admin_queue_keyset_pages_and_invalid_cursor(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    for _ in range(3):
        await _insert_duplicate_pair_with_entry(app_database_url)
    await register_and_login(email="admin-pagination@example.com", role="ADMINISTRATOR")
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(3):
        params = {"limit": "1"}
        if cursor:
            params["cursor"] = cursor
        response = await client.get("/api/v1/admin/duplicate-review", params=params)
        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        seen.append(body["items"][0]["id"])
        cursor = body["nextCursor"]
    assert len(set(seen)) == 3 and cursor is None
    bad = await client.get("/api/v1/admin/duplicate-review", params={"cursor": "not-valid"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
