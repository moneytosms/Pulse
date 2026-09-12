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

    resp = await client.get(
        "/api/v1/audit-events", params={"patientId": str(other_patient_id)}
    )
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
