"""Modules use their own models or composable service predicates, never raw SQL.

Raw SQL remains available to migrations and the seed loader. Banning it in
modules closes the table-ownership bypass that import checks cannot see.
"""

import ast
from pathlib import Path

_MODULES = Path(__file__).resolve().parents[1] / "app/modules"


def raw_sql_calls(source: str) -> list[int]:
    tree = ast.parse(source)
    aliases = {"text", "exec_driver_sql"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("sqlalchemy"):
            aliases.update(
                alias.asname or alias.name for alias in node.names if alias.name == "text"
            )
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if (isinstance(function, ast.Name) and function.id in aliases) or (
                isinstance(function, ast.Attribute) and function.attr in {"text", "exec_driver_sql"}
            ):
                lines.append(node.lineno)
    return lines


def main() -> int:
    failures = [
        f"{path.relative_to(_MODULES.parent.parent)}:{line}: raw SQL bypasses module ownership"
        for path in sorted(_MODULES.rglob("*.py"))
        for line in raw_sql_calls(path.read_text())
    ]
    for failure in failures:
        print(failure)
    if not failures:
        print("clean — modules use owned models or explicit service query seams")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
