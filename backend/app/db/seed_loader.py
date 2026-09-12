"""First-boot seed loader: identity, then Medical Entries.

Invoked by the backend container entrypoint after ``alembic upgrade head``
and before ``uvicorn``. Loads the committed, deterministic dataset in
``seed/data/identity/`` -- Provider, ProviderStaff, User, Patient -- and
``seed/data/clinical/`` -- a capped selection of Medical Entries (P2.4,
"seed part 2") so the timeline is non-empty on a fresh clone. The clinical
CSVs are Synthea output, already remapped onto these Patient ids by
``seed/scripts/build.py``; every coded field loaded here is a real
``(code_system, code)`` pair taken straight from that data -- SNOMED-CT
(conditions), LOINC (observations), RxNorm (medications). No code is
invented; reference ranges for a small set of common LOINC panels are the
one piece of external clinical knowledge added at load time, matching the
values already used in the P2.3-era test fixtures.

Idempotent: a single ``seed_marker`` row (migration 0003) is written at
the end of a successful load, covering both identity and clinical rows in
one transaction. A second run finds it and returns without touching a
table, so a second ``docker compose up`` is a no-op.

The committed CSVs carry no password hashes -- argon2 output is
non-deterministic and would break the "regenerate -> git diff empty"
contract (ADR-0015). Instead, ``users.csv`` flags demo logins; this
loader stamps a hash of the public dev password and ``email_verified_at``
for those rows at load time. Every other seeded User shares one hash of a
random secret -- a NOT NULL value no password can satisfy. Argon2 runs
exactly twice per boot, not once per row.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import os
import secrets
import uuid
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import Role
from app.core.security import hash_password
from app.db.session import async_session
from app.modules.records.models import Diagnosis, EntryType, LabReport, Prescription, Procedure
from app.modules.users.models import Patient, Provider, ProviderKind, ProviderStaff, Sex, User

# Public demo credential -- this project never holds real patient data
# (clinical-safety.md). Mirrors seed/scripts/common.DEV_PASSWORD.
DEV_PASSWORD = "Pulse@demo1"  # documented public demo credential
VERIFIED_AT = datetime.fromisoformat("2026-01-01T00:00:00+00:00")

# Argon2 is deliberately slow; hash exactly twice per boot, not once per row.
# Every demo user shares DEV_PASSWORD, and every non-demo user just needs a
# NOT NULL value that no password can satisfy.
_DEMO_HASH = hash_password(DEV_PASSWORD)
_UNUSABLE_HASH = hash_password(secrets.token_urlsafe(32))

# Local dev: repo_root/seed/data. Container: /seed/data (compose bind mount).
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "seed" / "data"

# Entries-per-patient cap for seed part 2 -- keeps first boot fast against
# ~120 patients (up to 10 entries each, ~1200 rows total) while still
# giving every entry type and both lab-value shapes real, non-trivial data.
_DIAGNOSIS_CAP = 3
_PROCEDURE_CAP = 2
_PRESCRIPTION_CAP = 2
_LAB_CAP = 3

# Standard adult reference intervals for a handful of common LOINC panel
# codes present in observations.csv (low, high, unit). Not invented codes
# -- the codes are the committed data; this is the one piece of external
# clinical knowledge layered on at load time (mirrors the 4548-4 range
# already hardcoded in tests/records_helpers.py).
_LAB_REFERENCE_RANGES: dict[str, tuple[float, float, str]] = {
    "2339-0": (70.0, 99.0, "mg/dL"),  # Glucose
    "2345-7": (70.0, 99.0, "mg/dL"),  # Glucose
    "4548-4": (4.0, 5.6, "%"),  # Hemoglobin A1c
    "2160-0": (0.6, 1.3, "mg/dL"),  # Creatinine
    "6690-2": (4.0, 11.0, "10*3/uL"),  # Leukocytes
    "718-7": (12.0, 17.5, "g/dL"),  # Hemoglobin
    "2093-3": (125.0, 200.0, "mg/dL"),  # Total Cholesterol
    "2951-2": (136.0, 145.0, "mmol/L"),  # Sodium
    "6298-4": (3.5, 5.1, "mmol/L"),  # Potassium
}

# Synthea's own derived quality-of-life scores -- not a LOINC vocabulary.
_SKIP_OBSERVATION_CODES = {"QALY", "DALY", "QOLS"}

# uuid5 namespace for entries derived at load time -- deterministic given
# the same committed clinical CSVs, independent of seed/scripts/common.py
# (backend never depends on the generation-time package).
_ENTRY_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "seed-entries.pulse.local")


class SeedResult:
    def __init__(self, *, skipped: bool, counts: dict[str, int]) -> None:
        self.skipped = skipped
        self.counts = counts

    def __str__(self) -> str:
        if self.skipped:
            return "seed: seed_marker present -- nothing to do"
        c = self.counts
        return (
            "seed: loaded "
            f"{c['providers']} providers, {c['provider_staff']} staff, "
            f"{c['users']} users, {c['patients']} patients "
            f"({c['patients_unclaimed']} unclaimed); "
            f"{c['diagnoses']} diagnoses, {c['procedures']} procedures, "
            f"{c['prescriptions']} prescriptions, {c['lab_reports']} lab reports"
        )


def _data_dir() -> Path:
    return Path(os.environ.get("SEED_DATA_DIR", _DEFAULT_DATA_DIR))


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _dataset_checksum(*dirs: Path) -> str:
    h = hashlib.sha256()
    for d in dirs:
        for name in sorted(p.name for p in d.glob("*.csv")):
            h.update((d / name).read_bytes())
    return h.hexdigest()


async def _already_loaded(session: AsyncSession) -> bool:
    result = await session.execute(text("SELECT count(*) FROM seed_marker"))
    return bool(result.scalar_one())


def _entry_uuid(*parts: str) -> uuid.UUID:
    return uuid.uuid5(_ENTRY_NS, "|".join(parts))


def _occurred_at(raw: str) -> datetime:
    if "T" in raw:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    return datetime.fromisoformat(raw + "T00:00:00+00:00")  # conditions.csv: date only


def _group_by_patient(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for r in rows:
        grouped.setdefault(r["patient"], []).append(r)
    return grouped


def _build_coded_entries(
    cls: type[Diagnosis] | type[Procedure],
    rows: list[dict[str, str]],
    patient_id: str,
    entry_type: EntryType,
    cap: int,
    csv_name: str,
    source_provider_id: uuid.UUID,
) -> list[Diagnosis | Procedure]:
    """Diagnosis/Procedure share a shape: SNOMED-CT (code_system, code) plus
    a display name, straight from conditions.csv / procedures.csv."""
    picked = sorted(rows, key=lambda r: (r["start"], r["code"]))[:cap]
    return [
        cls(
            id=_entry_uuid(entry_type.value, patient_id, r["code"], r["start"]),
            patient_id=uuid.UUID(patient_id),
            entry_type=entry_type,
            source_provider_id=source_provider_id,
            occurred_at=_occurred_at(r["start"]),
            entry_metadata={"import_batch": "seed-part-2", "source": csv_name},
            code_system=r["system"],
            code=r["code"],
            display_name=r["description"],
        )
        for r in picked
    ]


def _build_prescriptions(
    rows: list[dict[str, str]],
    patient_id: str,
    cap: int,
    source_provider_id: uuid.UUID,
) -> list[Prescription]:
    picked = sorted(rows, key=lambda r: (r["start"], r["code"]))[:cap]
    return [
        Prescription(
            id=_entry_uuid("PRESCRIPTION", patient_id, r["code"], r["start"]),
            patient_id=uuid.UUID(patient_id),
            entry_type=EntryType.PRESCRIPTION,
            source_provider_id=source_provider_id,
            occurred_at=_occurred_at(r["start"]),
            entry_metadata={"import_batch": "seed-part-2", "source": "medications.csv"},
            medication_name=r["description"],
            code_system="RxNorm",
            code=r["code"],
            display_name=r["description"],
        )
        for r in picked
    ]


def _is_out_of_range(value: float, low: float, high: float) -> bool:
    return value < low or value > high


def _pick_lab_rows(
    rows: list[dict[str, str]], cap: int
) -> list[dict[str, str]]:
    """At least one out-of-range numeric result (if the patient has one for
    a known panel) and at least one text result are prioritised first, so
    the seeded dataset as a whole always carries both lab-value shapes."""
    candidates = sorted(
        (r for r in rows if r["code"] not in _SKIP_OBSERVATION_CODES),
        key=lambda r: (r["date"], r["code"]),
    )
    numeric_known = [
        r
        for r in candidates
        if r["type"] == "numeric" and r["code"] in _LAB_REFERENCE_RANGES
    ]
    numeric_other = [
        r
        for r in candidates
        if r["type"] == "numeric" and r["code"] not in _LAB_REFERENCE_RANGES
    ]
    text_rows = [r for r in candidates if r["type"] != "numeric"]
    out_of_range = [
        r
        for r in numeric_known
        if _is_out_of_range(float(r["value"]), *_LAB_REFERENCE_RANGES[r["code"]][:2])
    ]

    picks: list[dict[str, str]] = []
    if out_of_range:
        picks.append(out_of_range[0])
    elif numeric_known:
        picks.append(numeric_known[0])
    if text_rows and text_rows[0] not in picks:
        picks.append(text_rows[0])
    for pool in (numeric_known, numeric_other, text_rows):
        for r in pool:
            if len(picks) >= cap:
                break
            if r not in picks:
                picks.append(r)
    return picks[:cap]


def _build_lab_reports(
    rows: list[dict[str, str]],
    patient_id: str,
    cap: int,
    source_provider_id: uuid.UUID,
) -> list[LabReport]:
    out = []
    for r in _pick_lab_rows(rows, cap):
        is_numeric = r["type"] == "numeric"
        ref = _LAB_REFERENCE_RANGES.get(r["code"])
        out.append(
            LabReport(
                id=_entry_uuid("LAB_REPORT", patient_id, r["code"], r["date"]),
                patient_id=uuid.UUID(patient_id),
                entry_type=EntryType.LAB_REPORT,
                source_provider_id=source_provider_id,
                occurred_at=_occurred_at(r["date"]),
                entry_metadata={"import_batch": "seed-part-2", "source": "observations.csv"},
                code_system="LOINC",
                code=r["code"],
                display_name=r["description"],
                value_numeric=float(r["value"]) if is_numeric else None,
                value_text=None if is_numeric else r["value"],
                unit=ref[2] if ref else (r["units"] or None),
                reference_low=ref[0] if ref else None,
                reference_high=ref[1] if ref else None,
            )
        )
    return out


def _dedupe_new(
    objs: list[Diagnosis | Procedure] | list[Prescription] | list[LabReport],
    seen_ids: set[uuid.UUID],
) -> list[object]:
    """A handful of source rows repeat verbatim (e.g. medications.csv has a
    few (patient, start, code) duplicates) -- same input, same deterministic
    id. Drop the repeat rather than fail the unique constraint."""
    keep: list[object] = []
    for o in objs:
        if o.id in seen_ids:
            continue
        seen_ids.add(o.id)
        keep.append(o)
    return keep


def _provider_for_patient(pid: str, provider_ids: list[uuid.UUID]) -> uuid.UUID:
    """Deterministic patient -> Provider assignment. Synthea's trimmed
    encounters.csv carries no provider column, so every seeded Entry needs
    one invented here rather than left NULL — Phase 3 rule 2
    (`accessible_entries`) narrows Provider Staff to entries authored by
    their own Provider, and a NULL `source_provider_id` would match no
    Provider Staff at all, including the demo login. Hash-based so it is
    stable across seed runs without being recorded anywhere."""
    return provider_ids[uuid.UUID(pid).int % len(provider_ids)]


def _build_clinical_entries(
    clinical_dir: Path, patient_ids: list[str], provider_ids: list[uuid.UUID]
) -> tuple[list[object], dict[str, int]]:
    """A capped, deterministic selection of Medical Entries per Patient,
    read from the already patient-id-remapped `seed/data/clinical/*.csv`
    (build.py's `transform_clinical`). Planted duplicate Patients carry no
    clinical rows in that data, so they simply get none here too."""
    conditions = _group_by_patient(_rows(clinical_dir / "conditions.csv"))
    procedures = _group_by_patient(_rows(clinical_dir / "procedures.csv"))
    medications = _group_by_patient(_rows(clinical_dir / "medications.csv"))
    observations = _group_by_patient(_rows(clinical_dir / "observations.csv"))

    entries: list[object] = []
    seen_ids: set[uuid.UUID] = set()
    counts = {"diagnoses": 0, "procedures": 0, "prescriptions": 0, "lab_reports": 0}
    for pid in sorted(patient_ids):
        provider_id = _provider_for_patient(pid, provider_ids)
        diagnoses = _dedupe_new(
            _build_coded_entries(
                Diagnosis, conditions.get(pid, []), pid, EntryType.DIAGNOSIS,
                _DIAGNOSIS_CAP, "conditions.csv", provider_id,
            ),
            seen_ids,
        )
        procs = _dedupe_new(
            _build_coded_entries(
                Procedure, procedures.get(pid, []), pid, EntryType.PROCEDURE,
                _PROCEDURE_CAP, "procedures.csv", provider_id,
            ),
            seen_ids,
        )
        rx = _dedupe_new(
            _build_prescriptions(
                medications.get(pid, []), pid, _PRESCRIPTION_CAP, provider_id
            ),
            seen_ids,
        )
        labs = _dedupe_new(
            _build_lab_reports(observations.get(pid, []), pid, _LAB_CAP, provider_id),
            seen_ids,
        )
        entries.extend([*diagnoses, *procs, *rx, *labs])
        counts["diagnoses"] += len(diagnoses)
        counts["procedures"] += len(procs)
        counts["prescriptions"] += len(rx)
        counts["lab_reports"] += len(labs)
    return entries, counts


def _build_objects(identity_dir: Path) -> tuple[list[object], dict[str, int]]:
    providers = [
        Provider(
            id=uuid.UUID(r["id"]),
            name=r["name"],
            kind=ProviderKind(r["kind"]),
            city=r["city"],
            state=r["state"],
        )
        for r in _rows(identity_dir / "providers.csv")
    ]

    users = []
    for r in _rows(identity_dir / "users.csv"):
        demo = r["demo_login"] == "1"
        users.append(
            User(
                id=uuid.UUID(r["id"]),
                email=r["email"],
                password_hash=_DEMO_HASH if demo else _UNUSABLE_HASH,
                role=Role(r["role"]),
                email_verified_at=VERIFIED_AT if demo else None,
            )
        )

    patients = []
    unclaimed = 0
    for r in _rows(identity_dir / "patients.csv"):
        uid = r["user_id"] or None
        if uid is None:
            unclaimed += 1
        patients.append(
            Patient(
                id=uuid.UUID(r["id"]),
                user_id=uuid.UUID(uid) if uid else None,
                full_name=r["full_name"],
                date_of_birth=date.fromisoformat(r["date_of_birth"])
                if r["date_of_birth"]
                else None,
                sex=Sex(r["sex"]) if r["sex"] else None,
                phone=r["phone"] or None,
                address_line=r["address_line"] or None,
                city=r["city"] or None,
                state=r["state"] or None,
                locale_preference=r["locale_preference"] or "en",
            )
        )

    staff = [
        ProviderStaff(
            id=uuid.UUID(r["id"]),
            user_id=uuid.UUID(r["user_id"]),
            provider_id=uuid.UUID(r["provider_id"]),
        )
        for r in _rows(identity_dir / "provider_staff.csv")
    ]

    counts = {
        "providers": len(providers),
        "provider_staff": len(staff),
        "users": len(users),
        "patients": len(patients),
        "patients_unclaimed": unclaimed,
    }
    # users + providers before patients + staff (FK order).
    return [*providers, *users, *patients, *staff], counts


async def run_seed() -> SeedResult:
    identity_dir = _data_dir() / "identity"
    clinical_dir = _data_dir() / "clinical"
    if not (identity_dir / "patients.csv").is_file():
        raise FileNotFoundError(f"seed dataset not found under {identity_dir}")

    async with async_session() as session:
        if await _already_loaded(session):
            return SeedResult(skipped=True, counts={})

        objects, counts = _build_objects(identity_dir)
        session.add_all(objects)
        await session.flush()  # Patients committed to the flush before entries FK to them

        patient_ids = [r["id"] for r in _rows(identity_dir / "patients.csv")]
        provider_ids = [
            uuid.UUID(r["id"]) for r in _rows(identity_dir / "providers.csv")
        ]
        entry_objects, entry_counts = _build_clinical_entries(
            clinical_dir, patient_ids, provider_ids
        )
        counts.update(entry_counts)
        session.add_all(entry_objects)
        await session.flush()

        await session.execute(
            text(
                "INSERT INTO seed_marker (id, dataset_sha256) VALUES (1, :h)"
            ),
            {"h": _dataset_checksum(identity_dir, clinical_dir)},
        )
        await session.commit()
        return SeedResult(skipped=False, counts=counts)


async def _main() -> None:
    result = await run_seed()
    print(result)


if __name__ == "__main__":
    asyncio.run(_main())
