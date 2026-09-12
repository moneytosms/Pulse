"""P2.7 — a correction inserts a new Medical Entry and stamps
``superseded_by_id`` on the original. No clinical row is ever updated in place
(clinical-safety.md, ADR-0001).

ASGI-client seam. Written red — neither the tables nor the corrections route
exist yet. Negatives first: the original stays byte-identical, a second
correction of the same original is a 409.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

_PW = "correct-horse-staple-9"

_CORRECTION_BODY = {
    "entryType": "LAB_REPORT",
    "codeSystem": "http://loinc.org",
    "code": "4548-4",
    "displayName": "Hemoglobin A1c",
    "valueNumeric": 5.4,
    "unit": "%",
    "referenceLow": 4.0,
    "referenceHigh": 5.6,
    "occurredAt": "2025-02-02T00:00:00Z",
}


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


async def _patient_entry_and_staff(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> tuple[str, str]:
    await register_and_login(email="corr-patient@example.com")
    pid = str((await client.get("/api/v1/patients/me")).json()["id"])
    await register_and_login(email="corr-staff@example.com", role="PROVIDER_STAFF")
    # Provider must match the entry's `source_provider_id` — Phase 3 rule 2
    # (`accessible_entries`) narrows Provider Staff to their own Provider.
    provider_id = await rh.seed_provider_staff(
        app_database_url, user_email="corr-staff@example.com"
    )
    entry_id = str(
        await rh.insert_entry(
            app_database_url,
            patient_id=pid,  # type: ignore[arg-type]
            occurred_at=datetime(2025, 2, 2, tzinfo=UTC),
            entry_type="LAB_REPORT",
            value_numeric=15.4,  # the wrong value being corrected
            source_provider_id=provider_id,
        )
    )
    return pid, entry_id


async def test_correction_supersedes_without_touching_the_original(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_entry_and_staff(
        client, register_and_login, app_database_url
    )
    before = await client.get(f"/api/v1/entries/{entry_id}")
    assert before.status_code == 200
    original_recorded_at = before.json()["recordedAt"]

    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/corrections",
        json=_CORRECTION_BODY,
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]
    assert resp.json()["supersedesId"] == entry_id

    after = await client.get(f"/api/v1/entries/{entry_id}")
    assert after.status_code == 200
    body = after.json()
    assert body["supersededById"] == new_id
    assert body["valueNumeric"] == 15.4  # unchanged
    assert body["recordedAt"] == original_recorded_at  # no in-place update


async def test_timeline_shows_the_correction_not_the_original(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_entry_and_staff(
        client, register_and_login, app_database_url
    )
    new_id = (
        await client.post(
            f"/api/v1/patients/{pid}/entries/{entry_id}/corrections",
            json=_CORRECTION_BODY,
        )
    ).json()["id"]

    await register_and_login(email="corr-patient@example.com")
    listing = await client.get(f"/api/v1/patients/{pid}/entries")
    assert listing.status_code == 200
    ids = {item["id"] for item in listing.json()["items"]}
    assert new_id in ids
    assert entry_id not in ids


async def test_second_correction_of_the_same_entry_is_409(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_entry_and_staff(
        client, register_and_login, app_database_url
    )
    first = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/corrections", json=_CORRECTION_BODY
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/corrections", json=_CORRECTION_BODY
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ENTRY_ALREADY_SUPERSEDED"


async def test_clinician_cannot_correct(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_entry_and_staff(
        client, register_and_login, app_database_url
    )
    await register_and_login(email="corr-clin@example.com", role="CLINICIAN")
    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/corrections", json=_CORRECTION_BODY
    )
    assert resp.status_code in (403, 404)
