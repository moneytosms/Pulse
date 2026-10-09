"""An import-clean module must still be unable to read another domain with raw SQL."""

import importlib.util
from pathlib import Path


def test_raw_sql_bypass_and_aliases_are_rejected() -> None:
    spec = importlib.util.spec_from_file_location(
        "sql_lint", Path(__file__).parents[1] / "scripts/lint_module_sql.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.raw_sql_calls(
        "from sqlalchemy import text as sql\n"
        'session.execute(sql("SELECT * FROM access_permission"))'
    ) == [2]
    assert module.raw_sql_calls('session.exec_driver_sql("SELECT * FROM medical_entry")') == [1]
    assert (
        module.raw_sql_calls(
            "session.execute(consent_service.clinical_access_predicate("
            "patient_id, actor.user_id, entry_type, occurred_at))"
        )
        == []
    )
