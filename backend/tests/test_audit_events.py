"""P3.8 (#45) — real audit emission + the Patient's filtered projection.

ASGI-client seam for emission (exercises `records/service.py`'s wiring
together with `audit/service.emit`); `audit_helpers` raw SQL to inspect
the stored row directly for the metadata-never-clinical negative test —
a mock or a schema-shape assertion would pass just as happily if a
clinical field leaked into `event_metadata` in practice.

Negative first (backend.md): no clinical value in `audit_event.metadata`,
ever; a denied read emits nothing; another patient's events, and raw
identifiers, never appear in the Patient's own projection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import audit_helpers as ah
import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def test_actor_and_until_filters_do_not_leak_or_skip_pages(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-ux-filter@example.com")
    pid = await _patient_id(client)
    for role, hour in [("CLINICIAN", 9), ("PATIENT", 10), ("CLINICIAN", 11), ("CLINICIAN", 12)]:
        await ah.seed_event_for_patient(
            app_database_url,
            patient_id=pid,
            actor_role=role,
            occurred_at=datetime(2026, 10, 9, hour, tzinfo=UTC),
        )
    query = {
        "actorRole": "CLINICIAN",
        "since": "2026-10-09T00:00:00Z",
        "until": "2026-10-09T12:00:00Z",
        "limit": "1",
    }
    first = await client.get("/api/v1/audit-events", params=query)
    assert first.status_code == 200
    assert first.json()["items"][0]["occurredAt"].startswith("2026-10-09T11:")
    assert first.json()["items"][0]["isSelf"] is False
    query["cursor"] = first.json()["nextCursor"]
    second = await client.get("/api/v1/audit-events", params=query)
    assert second.json()["items"][0]["occurredAt"].startswith("2026-10-09T09:")
    assert second.json()["nextCursor"] is None
    await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2026, 10, 1, tzinfo=UTC)
    )
    await client.get(f"/api/v1/patients/{pid}/entries")
    self_events = await client.get("/api/v1/audit-events", params={"actorRole": "PATIENT"})
    assert any(row["isSelf"] for row in self_events.json()["items"])


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await ah.wipe_audit_events(app_database_url)
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


async def _patient_id(client: AsyncClient) -> UUID:
    resp = await client.get("/api/v1/patients/me")
    resp.raise_for_status()
    return UUID(str(resp.json()["id"]))


# --- negative: metadata never carries clinical content ---------------------

DISPLAY_NAME = "Hemoglobin A1c"
OWN_CODE = "4548-4"
CLINICAL_VALUE = 7.8


async def test_get_entry_audit_row_carries_no_clinical_value(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-clinical-1@example.com")
    pid = await _patient_id(client)
    entry_id = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=datetime(2025, 2, 2, tzinfo=UTC),
        entry_type="LAB_REPORT",
        code=OWN_CODE,
        display_name=DISPLAY_NAME,
        value_numeric=CLINICAL_VALUE,
        unit="%",
    )

    resp = await client.get(f"/api/v1/entries/{entry_id}")
    assert resp.status_code == 200

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    assert len(rows) == 1
    metadata = rows[0]["metadata"]
    # Whitelist: only the small typed field set `AuditMetadata` allows.
    assert set(metadata.keys()) <= {"entry_type", "provider_name", "count", "justification"}
    # And the actual clinical values are nowhere in the stored row.
    blob = str(rows[0])
    assert DISPLAY_NAME not in blob
    assert OWN_CODE not in blob
    assert str(CLINICAL_VALUE) not in blob


async def test_timeline_read_emits_exactly_one_entry_viewed_regardless_of_page_size(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-timeline-count@example.com")
    pid = await _patient_id(client)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for _ in range(5):
        await rh.insert_entry(app_database_url, patient_id=pid, occurred_at=base)

    resp = await client.get(f"/api/v1/patients/{pid}/entries")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 5

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    entry_viewed = [r for r in rows if r["action"] == "ENTRY_VIEWED" and r["resource_id"] is None]
    assert len(entry_viewed) == 1
    assert entry_viewed[0]["metadata"]["count"] == 5


async def test_timeline_read_with_a_smaller_page_still_emits_exactly_one_event(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-timeline-page@example.com")
    pid = await _patient_id(client)
    base = datetime(2025, 1, 1, tzinfo=UTC)
    for _ in range(3):
        await rh.insert_entry(app_database_url, patient_id=pid, occurred_at=base)

    resp = await client.get(f"/api/v1/patients/{pid}/entries?limit=1")
    assert resp.status_code == 200

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    entry_viewed = [r for r in rows if r["action"] == "ENTRY_VIEWED"]
    assert len(entry_viewed) == 1


async def test_get_entry_emits_one_entry_viewed_scoped_to_that_entry(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-get-entry@example.com")
    pid = await _patient_id(client)
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 3, 1, tzinfo=UTC)
    )

    resp = await client.get(f"/api/v1/entries/{entry_id}")
    assert resp.status_code == 200

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    assert len(rows) == 1
    assert rows[0]["action"] == "ENTRY_VIEWED"
    assert str(rows[0]["resource_id"]) == str(entry_id)
    assert rows[0]["outcome"] == "SUCCESS"


async def test_denied_read_emits_no_audit_event(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-denied-patient@example.com")
    pid = await _patient_id(client)
    entry_id = await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 3, 1, tzinfo=UTC)
    )

    # A Clinician with no Consent/break-glass at all.
    await register_and_login(email="audit-denied-clinician@example.com", role="CLINICIAN")
    denied = await client.get(f"/api/v1/entries/{entry_id}")
    assert denied.status_code == 404

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    assert rows == []


# --- the Patient's own filtered projection ----------------------------------


async def test_projection_excludes_another_patients_events(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-proj-self@example.com")
    pid = await _patient_id(client)
    other_patient_id = await ah.insert_bare_patient(app_database_url)
    await ah.seed_event_for_patient(app_database_url, patient_id=pid)
    await ah.seed_event_for_patient(app_database_url, patient_id=other_patient_id)

    resp = await client.get("/api/v1/audit-events", params={"patientId": str(pid)})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1


async def test_projection_rejects_a_patient_id_that_is_not_the_callers_own(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-proj-mismatch@example.com")
    other_patient_id = await ah.insert_bare_patient(app_database_url)
    await ah.seed_event_for_patient(app_database_url, patient_id=other_patient_id)

    resp = await client.get("/api/v1/audit-events", params={"patientId": str(other_patient_id)})
    assert resp.status_code == 404


async def test_projection_never_exposes_raw_identifiers(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-proj-fields@example.com")
    pid = await _patient_id(client)
    await ah.seed_event_for_patient(app_database_url, patient_id=pid)

    resp = await client.get("/api/v1/audit-events", params={"patientId": str(pid)})
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    # Exactly the wire contract's field set — no patientId, actorUserId, or
    # any other raw identifier smuggled in.
    assert set(item.keys()) == {
        "id",
        "occurredAt",
        "actorName",
        "actorRole",
        "isSelf",
        "providerName",
        "action",
        "entryType",
    }
    assert "patientId" not in item
    assert "actorUserId" not in item


async def test_projection_reflects_a_real_entry_view_end_to_end(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-proj-e2e@example.com")
    pid = await _patient_id(client)
    entry_id = await rh.insert_entry(
        app_database_url,
        patient_id=pid,
        occurred_at=datetime(2025, 4, 1, tzinfo=UTC),
        entry_type="LAB_REPORT",
    )
    view = await client.get(f"/api/v1/entries/{entry_id}")
    assert view.status_code == 200

    resp = await client.get("/api/v1/audit-events", params={"patientId": str(pid)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["action"] == "ENTRY_VIEWED"
    assert items[0]["entryType"] == "LAB_REPORT"
    assert items[0]["actorRole"] == "PATIENT"


async def test_get_document_emits_one_document_viewed(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    import importlib

    deps = importlib.import_module("app.modules.records.dependencies")
    main = importlib.import_module("app.main")

    class _TmpStorage:
        def __init__(self) -> None:
            self._store: dict[str, bytes] = {}

        async def put(self, key: str, data: bytes, content_type: str) -> str:
            self._store[key] = data
            return key

        async def get(self, path: str) -> bytes:
            return self._store[path]

    storage = _TmpStorage()
    main.app.dependency_overrides[deps.get_storage_provider] = lambda: storage
    try:
        await register_and_login(email="audit-doc-patient@example.com")
        pid = str(await _patient_id(client))
        await register_and_login(email="audit-doc-staff@example.com", role="PROVIDER_STAFF")
        provider_id = await rh.seed_provider_staff(
            app_database_url, user_email="audit-doc-staff@example.com"
        )
        entry_id = await rh.insert_entry(
            app_database_url,
            patient_id=pid,  # type: ignore[arg-type]
            occurred_at=datetime(2025, 5, 1, tzinfo=UTC),
            entry_type="LAB_REPORT",
            source_provider_id=provider_id,
        )
        up = await client.post(
            f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
            files={"file": ("report.pdf", _PDF, "application/pdf")},
        )
        assert up.status_code == 201
        document_id = up.json()["id"]

        served = await client.get(f"/api/v1/documents/{document_id}")
        assert served.status_code == 200

        rows = await ah.fetch_events_for_patient(app_database_url, UUID(pid))
        doc_viewed = [r for r in rows if r["action"] == "DOCUMENT_VIEWED"]
        assert len(doc_viewed) == 1
        assert str(doc_viewed[0]["resource_id"]) == str(document_id)
    finally:
        main.app.dependency_overrides.pop(deps.get_storage_provider, None)


async def test_audit_row_carries_the_http_request_id(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-request-id@example.com")
    pid = await _patient_id(client)
    await rh.insert_entry(
        app_database_url, patient_id=pid, occurred_at=datetime(2025, 1, 1, tzinfo=UTC)
    )

    resp = await client.get(
        f"/api/v1/patients/{pid}/entries", headers={"X-Request-Id": "req-audit-42"}
    )
    assert resp.status_code == 200

    rows = await ah.fetch_events_for_patient(app_database_url, pid)
    assert [r["request_id"] for r in rows] == ["req-audit-42"]


async def test_oversized_client_request_id_is_replaced_not_a_500(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    await register_and_login(email="audit-request-id-long@example.com")
    pid = await _patient_id(client)

    resp = await client.get(f"/api/v1/patients/{pid}/entries", headers={"X-Request-Id": "x" * 500})
    assert resp.status_code == 200
    [row] = await ah.fetch_events_for_patient(app_database_url, pid)
    assert row["request_id"] == resp.headers["X-Request-Id"]
    assert len(row["request_id"]) <= 64


async def test_emergency_filter_excludes_old_and_other_patients_events(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    from datetime import timedelta

    await register_and_login(email="audit-emergency-filter@example.com")
    pid = await _patient_id(client)
    other = await ah.insert_bare_patient(app_database_url)
    now = datetime.now(UTC)
    await ah.seed_event_for_patient(
        app_database_url, patient_id=other, action="BREAK_GLASS_ACCESS", occurred_at=now
    )
    await ah.seed_event_for_patient(
        app_database_url,
        patient_id=pid,
        action="BREAK_GLASS_ACCESS",
        occurred_at=now - timedelta(hours=73),
    )
    params = {
        "action": "BREAK_GLASS_ACCESS",
        "since": (now - timedelta(hours=72)).isoformat(),
        "limit": "1",
    }
    absent = await client.get("/api/v1/audit-events", params=params)
    assert absent.status_code == 200
    assert absent.json()["items"] == []
    params["patientId"] = str(other)
    denied = await client.get("/api/v1/audit-events", params=params)
    assert denied.status_code == 404
    del params["patientId"]

    recent = await ah.seed_event_for_patient(
        app_database_url,
        patient_id=pid,
        action="BREAK_GLASS_ACCESS",
        occurred_at=now - timedelta(hours=1),
    )
    for _ in range(7):
        await ah.seed_event_for_patient(app_database_url, patient_id=pid, occurred_at=now)
    found = await client.get("/api/v1/audit-events", params=params)
    assert found.status_code == 200
    assert [item["id"] for item in found.json()["items"]] == [str(recent)]


async def test_audit_filter_rejects_naive_timestamp(
    client: AsyncClient, register_and_login: RegisterAndLogin
) -> None:
    await register_and_login(email="audit-naive-filter@example.com")
    response = await client.get("/api/v1/audit-events", params={"since": "2026-10-01T00:00:00"})
    assert response.status_code == 422
