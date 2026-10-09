"""Entry-query lint (ADR-0006).

Every read of Medical Entries composes from `accessible_entries(...)` in
`app/modules/records/repository.py`. A raw `select(MedicalEntry)` or
`.query(MedicalEntry)` anywhere else is a fresh unfiltered query — the
exact failure this lint exists to catch.

`MedicalEntry` has no model yet (Phase 2), so today this is armed and
finds nothing. Prints an explicit line and exits 0; exits 1 the moment a
match appears outside the one repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_APP_DIR = _BACKEND_DIR / "app"
_EXEMPT = _APP_DIR / "modules" / "records" / "repository.py"

_PATTERN = re.compile(r"\bselect\(\s*MedicalEntry\b|\.query\(\s*MedicalEntry\b")


def main() -> int:
    matches: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        if path == _EXEMPT:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _PATTERN.search(line):
                rel = path.relative_to(_BACKEND_DIR)
                matches.append(f"{rel}:{lineno} -> {line.strip()}")

    if not matches:
        print("clean — no MedicalEntry reads outside its repository")
        return 0

    for m in matches:
        print(m)
    print(
        f"{len(matches)} match(es) — select(MedicalEntry)/.query(MedicalEntry) "
        "outside app/modules/records/repository.py (ADR-0006)"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
