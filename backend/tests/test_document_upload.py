"""P2.6 — document upload: MIME allowlist with server-side sniffing, size cap,
checksum, and serve-behind-the-same-access-rule.

ASGI-client seam. A ``get_storage_provider`` dependency override onto ``tmp_path``
is applied when that dependency exists; until P2.6 lands it does not, and these
tests fail on the missing route. Written red, negatives first.
"""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
import records_helpers as rh
from helpers import RegisterAndLogin, wipe_identity
from httpx import AsyncClient

_PW = "correct-horse-staple-9"
_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
_SCRIPT = b"#!/bin/sh\necho totally-a-pdf\n"
_ZIP = b"PK\x03\x04\x14\x00\x00\x00\x00\x00fake-zip-body"


@pytest_asyncio.fixture(autouse=True)
async def _isolate(app_database_url: str) -> AsyncIterator[None]:
    yield
    await rh.wipe_records(app_database_url)
    await wipe_identity(app_database_url)


@pytest.fixture
def _storage_to_tmp(tmp_path: Path) -> Iterator[None]:
    """Point the storage adapter at tmp_path if the DI hook exists yet."""
    try:
        deps = importlib.import_module("app.modules.records.dependencies")
        main = importlib.import_module("app.main")
    except ModuleNotFoundError:
        yield
        return
    get_storage_provider = getattr(deps, "get_storage_provider", None)
    if get_storage_provider is None:
        yield
        return

    class _TmpStorage:
        async def put(self, key: str, data: bytes, content_type: str) -> str:
            dest = tmp_path / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            return str(dest)

        async def get(self, path: str) -> bytes:
            return Path(path).read_bytes()

    main.app.dependency_overrides[get_storage_provider] = lambda: _TmpStorage()
    yield
    main.app.dependency_overrides.pop(get_storage_provider, None)


async def _patient_with_entry(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> tuple[str, str]:
    await register_and_login(email="doc-patient@example.com")
    pid = str((await client.get("/api/v1/patients/me")).json()["id"])
    entry_id = await rh.insert_entry(
        app_database_url,
        patient_id=pid,  # type: ignore[arg-type]
        occurred_at=datetime(2025, 2, 2, tzinfo=UTC),
        entry_type="LAB_REPORT",
    )
    return pid, str(entry_id)


async def _become_provider_staff(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> str:
    await register_and_login(email="doc-staff@example.com", role="PROVIDER_STAFF")
    provider_id = await rh.seed_provider_staff(
        app_database_url, user_email="doc-staff@example.com"
    )
    return str(provider_id)


async def _patient_with_entry_authored_by_staff(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> tuple[str, str]:
    """Same as `_patient_with_entry`, but the Entry's `source_provider_id`
    matches the staff created by `_become_provider_staff` — Phase 3 rule 2
    (`accessible_entries`) narrows Provider Staff to their own Provider's
    entries, so upload/serve tests need the two to line up. Ends with the
    staff session active, since that's what every caller needs next."""
    await register_and_login(email="doc-patient@example.com")
    pid = str((await client.get("/api/v1/patients/me")).json()["id"])
    provider_id = await _become_provider_staff(client, register_and_login, app_database_url)
    entry_id = await rh.insert_entry(
        app_database_url,
        patient_id=pid,  # type: ignore[arg-type]
        occurred_at=datetime(2025, 2, 2, tzinfo=UTC),
        entry_type="LAB_REPORT",
        source_provider_id=provider_id,  # type: ignore[arg-type]
    )
    return pid, str(entry_id)


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_provider_staff_uploads_a_pdf_and_gets_a_checksum(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry_authored_by_staff(
        client, register_and_login, app_database_url
    )

    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("report.pdf", _PDF, "application/pdf")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["checksumSha256"] == hashlib.sha256(_PDF).hexdigest()
    assert body["sizeBytes"] == len(_PDF)


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_declared_pdf_with_script_body_is_rejected_on_its_bytes(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry(client, register_and_login, app_database_url)
    await _become_provider_staff(client, register_and_login, app_database_url)

    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("report.pdf", _SCRIPT, "application/pdf")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_disallowed_mime_type_is_rejected(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry(client, register_and_login, app_database_url)
    await _become_provider_staff(client, register_and_login, app_database_url)

    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("archive.zip", _ZIP, "application/zip")},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_oversized_upload_is_413(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry(client, register_and_login, app_database_url)
    await _become_provider_staff(client, register_and_login, app_database_url)

    # Larger than any sane document cap for a scanned report.
    huge = b"%PDF-1.4\n" + b"0" * (26 * 1024 * 1024)
    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("huge.pdf", huge, "application/pdf")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_patient_cannot_upload(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry(client, register_and_login, app_database_url)
    # still logged in as the patient
    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("report.pdf", _PDF, "application/pdf")},
    )
    assert resp.status_code == 403


async def test_unauthenticated_upload_is_401(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry(client, register_and_login, app_database_url)
    client.cookies.clear()
    resp = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("report.pdf", _PDF, "application/pdf")},
    )
    assert resp.status_code == 401


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_document_is_served_only_behind_the_entry_access_rule(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry_authored_by_staff(
        client, register_and_login, app_database_url
    )
    up = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("report.pdf", _PDF, "application/pdf")},
    )
    assert up.status_code == 201
    document_id = up.json()["id"]

    # A Clinician with no Consent must not be able to tell the document exists.
    await register_and_login(email="doc-clin@example.com", role="CLINICIAN")
    denied = await client.get(f"/api/v1/documents/{document_id}")
    assert denied.status_code == 404


@pytest.mark.usefixtures("_storage_to_tmp")
async def test_non_latin1_filename_is_served_not_a_500(
    client: AsyncClient, register_and_login: RegisterAndLogin, app_database_url: str
) -> None:
    pid, entry_id = await _patient_with_entry_authored_by_staff(
        client, register_and_login, app_database_url
    )
    up = await client.post(
        f"/api/v1/patients/{pid}/entries/{entry_id}/documents",
        files={"file": ("रिपोर्ट.pdf", _PDF, "application/pdf")},
    )
    assert up.status_code == 201

    served = await client.get(f"/api/v1/documents/{up.json()['id']}")
    assert served.status_code == 200
    assert served.content == _PDF
    # RFC 5987 extended form, not a latin-1 `filename="..."` that would 500.
    assert "filename*=UTF-8''" in served.headers["content-disposition"]
