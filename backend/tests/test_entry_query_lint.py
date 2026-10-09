"""The entry-query lint (ADR-0006) must pass while MedicalEntry is undefined."""

import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_entry_query.py"


def test_entry_query_lint_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no MedicalEntry reads outside its repository" in result.stdout
