"""P2.3 — cursor-paginated, polymorphic, superseded-filtered timeline read.

ASGI-client seam (exercises P2.3 + P2.5 together). Entries are seeded with raw
SQL; assertions are all on the HTTP response. Written red: neither the tables
nor ``GET /patients/{id}/entries`` exist yet.

Negative tests first — a superseded entry absent, pages that never overlap —
because each passes just as happily when the filter was never written.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

_PW = "correct-horse-staple-9"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


async def _patient_id(client: AsyncClient) -> UUID:
    resp = await client.get("/api/v1/patients/me")
    resp.raise_for_status()
    return UUID(str(resp.json()["id"]))


async def test_timeline_orders_by_occurred_at_desc(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="tl-order@example.com")
    pid = await _patient_id(client)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for days in (0, 30, 10):
        await rh.insert_entry(
            app_database_url,
            patient_id=pid,
            occurred_at=base + timedelta(days=days),
            recorded_at=base + timedelta(days=90),
        )

    resp = await client.get(f"/api/v1/patients/{pid}/entries")
    assert resp.status_code == 200
    occurred = [item["occurredAt"] for item in resp.json()["items"]]
    assert occurred == sorted(occurred, reverse=True)


async def test_superseded_entry_is_absent_but_reachable_by_id(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="tl-supersede@example.com")
    pid = await _patient_id(client)
    now = datetime(2025, 6, 1, tzinfo=UTC)
    correction = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=now,
    )
    original = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=now,
        superseded_by_id=correction,
    )

    listing = await client.get(f"/api/v1/patients/{pid}/entries")
    assert listing.status_code == 200
    ids = {item["id"] for item in listing.json()["items"]}
    assert str(original) not in ids
    assert str(correction) in ids

    detail = await client.get(f"/api/v1/entries/{original}")
    assert detail.status_code == 200
    assert detail.json()["supersededById"] == str(correction)


async def test_cursor_pages_do_not_overlap_or_skip(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="tl-cursor@example.com")
    pid = await _patient_id(client)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for i in range(5):
        await rh.insert_entry(
            app_database_url,
            patient_id=pid,
            occurred_at=base + timedelta(days=i),
        )

    first = await client.get(f"/api/v1/patients/{pid}/entries?limit=2")
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["nextCursor"]

    # An insert between pages must not shift the window.
    await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=base + timedelta(days=10),
    )

    second = await client.get(f"/api/v1/patients/{pid}/entries?limit=2&cursor={body['nextCursor']}")
    assert second.status_code == 200
    page1 = {i["id"] for i in body["items"]}
    page2 = {i["id"] for i in second.json()["items"]}
    assert page1.isdisjoint(page2)


async def test_entry_type_filter_narrows_the_timeline(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="tl-filter@example.com")
    pid = await _patient_id(client)
    now = datetime(2025, 3, 1, tzinfo=UTC)
    await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=now,
        entry_type="CLINICAL_NOTE",
    )
    await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=now,
        entry_type="LAB_REPORT",
    )

    resp = await client.get(f"/api/v1/patients/{pid}/entries?entryType=LAB_REPORT")
    assert resp.status_code == 200
    kinds = {item["entryType"] for item in resp.json()["items"]}
    assert kinds == {"LAB_REPORT"}


async def test_a_malformed_cursor_is_a_coded_422_not_a_500(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="tl-badcursor@example.com")
    pid = await _patient_id(client)
    # Valid base64, nonsense payload — must not reach an uncaught fromisoformat.
    resp = await client.get(f"/api/v1/patients/{pid}/entries?cursor=eHl6")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_search_and_dates_filter_before_pagination_without_audit_content(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    import audit_helpers as ah

    await register_and_login(email="tl-search@example.com")
    pid = await _patient_id(client)
    for year, note in [
        (2024, "Matching sensitive text"),
        (2025, "Other note"),
        (2025, "Matching sensitive text"),
        (2025, "Matching sensitive text"),
    ]:
        await rh.insert_entry(
            app_database_url,
            patient_id=pid,
            occurred_at=datetime(year, 3, 1, tzinfo=UTC),
            note_text=note,
        )
    params = {
        "q": "matching sensitive",
        "fromDate": "2025-01-01",
        "toDate": "2025-12-31",
        "limit": "1",
    }
    first = await client.get(f"/api/v1/patients/{pid}/entries", params=params)
    assert first.status_code == 200
    assert len(first.json()["items"]) == 1
    assert first.json()["nextCursor"]
    params["cursor"] = first.json()["nextCursor"]
    second = await client.get(f"/api/v1/patients/{pid}/entries", params=params)
    assert second.status_code == 200
    assert len(second.json()["items"]) == 1
    assert second.json()["nextCursor"] is None
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]
    assert "sensitive" not in str(await ah.fetch_events_for_patient(app_database_url, pid)).lower()
    await register_and_login(email="tl-search-denied@example.com", role="CLINICIAN")
    denied = await client.get(f"/api/v1/patients/{pid}/entries", params=params)
    assert denied.status_code == 404
    options = await client.get(f"/api/v1/patients/{pid}/entry-providers")
    assert options.status_code == 404


async def test_search_window_rejects_reversed_dates(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="tl-search-window@example.com")
    pid = await _patient_id(client)
    response = await client.get(
        f"/api/v1/patients/{pid}/entries", params={"fromDate": "2025-12-31", "toDate": "2025-01-01"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_provider_choices_and_summary_names_follow_actor_access(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="tl-provider-patient@example.com")
    pid = await _patient_id(client)
    await register_and_login(email="tl-provider-staff-a@example.com", role="PROVIDER_STAFF")
    first_provider = await rh.seed_provider_staff(
        app_database_url,
        user_email="tl-provider-staff-a@example.com",
        provider_name="Synthetic Clinic A",
    )
    await register_and_login(email="tl-provider-staff-b@example.com", role="PROVIDER_STAFF")
    second_provider = await rh.seed_provider_staff(
        app_database_url,
        user_email="tl-provider-staff-b@example.com",
        provider_name="Synthetic Clinic B",
    )
    for provider in [first_provider, second_provider]:
        await rh.insert_entry(
            app_database_url,
            patient_id=pid,
            source_provider_id=provider,
            occurred_at=datetime(2025, 6, 1, tzinfo=UTC),
        )
    # Staff B must not discover Provider A from another Provider's entries.
    options = await client.get(f"/api/v1/patients/{pid}/entry-providers")
    assert options.status_code == 200
    assert options.json() == [{"id": str(second_provider), "name": "Synthetic Clinic B"}]
    denied_filter = await client.get(
        f"/api/v1/patients/{pid}/entries", params={"providerId": str(first_provider)}
    )
    assert denied_filter.status_code == 200
    assert denied_filter.json()["items"] == []
    await register_and_login(email="tl-provider-patient@example.com")
    own = await client.get(
        f"/api/v1/patients/{pid}/entries", params={"providerId": str(first_provider)}
    )
    assert own.status_code == 200
    assert len(own.json()["items"]) == 1
    assert own.json()["items"][0]["providerName"] == "Synthetic Clinic A"
