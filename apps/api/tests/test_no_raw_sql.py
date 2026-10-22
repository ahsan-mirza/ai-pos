"""API code reaches the database only through ORM models.

Ruff's banned-api rule blocks raw-SQL imports (`sqlalchemy.text`, `sqlite3`, ...). This scan covers the call
sites ruff cannot see: `exec_driver_sql`, `execute()` with a SQL string, and `text()` reached through a module
alias such as `sa.text`. A genuine exception needs `# raw-sql: allowed (<reason>)` on the same line, and is only
accepted in the files listed in ALLOWED_FILES.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
MARKER = "# raw-sql: allowed"
ALLOWED_FILES = {"core/database.py"}
SQLALCHEMY_ALIASES = {"sa", "sqlalchemy", "sql", "expression"}
RAW_BUILDERS = {"text", "literal_column"}
HINT = "Use ORM models with select()/update()/delete() on a Session instead."


def _is_sql_string(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, str)
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp):
        return _is_sql_string(node.left) or _is_sql_string(node.right)
    return False


def raw_sql_calls(source: str) -> list[tuple[int, str]]:
    """(line, reason) for each raw-SQL call in `source`, ignoring lines that carry the allow marker."""
    lines = source.splitlines()
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        reason = None
        if isinstance(func, ast.Attribute):
            if func.attr == "exec_driver_sql":
                reason = "exec_driver_sql() sends raw SQL to the driver"
            elif func.attr in {"execute", "executemany"} and node.args and _is_sql_string(node.args[0]):
                reason = f"{func.attr}() called with a SQL string"
            elif func.attr in RAW_BUILDERS and isinstance(func.value, ast.Name) and func.value.id in SQLALCHEMY_ALIASES:
                reason = f"{func.value.id}.{func.attr}() builds raw SQL"
        if reason and MARKER not in lines[node.lineno - 1]:
            found.append((node.lineno, reason))
    return found


def _app_files() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def test_api_code_uses_orm_only() -> None:
    problems = [
        f"app/{path.relative_to(APP).as_posix()}:{line}: {reason}"
        for path in _app_files()
        for line, reason in raw_sql_calls(path.read_text(encoding="utf-8"))
    ]
    assert not problems, "Raw SQL found in the API. " + HINT + "\n" + "\n".join(problems)


def test_allow_marker_only_in_allowlisted_files() -> None:
    misuse = [
        f"app/{relative}:{number}"
        for path in _app_files()
        if (relative := path.relative_to(APP).as_posix()) not in ALLOWED_FILES
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if MARKER in line
    ]
    assert not misuse, f"'{MARKER}' is only accepted in {sorted(ALLOWED_FILES)}:\n" + "\n".join(misuse)


@pytest.mark.parametrize(
    "snippet",
    [
        'db.execute("SELECT * FROM products")',
        'db.execute(f"DELETE FROM sales WHERE id = {sale_id}")',
        'db.execute("UPDATE stores SET name = " + name)',
        'cursor.executemany("INSERT INTO t VALUES (?)", rows)',
        'connection.exec_driver_sql("VACUUM")',
        'db.execute(sa.text("SELECT 1"))',
        'query.order_by(sqlalchemy.literal_column("price"))',
    ],
)
def test_detector_flags_raw_sql(snippet: str) -> None:
    assert raw_sql_calls(snippet), snippet


@pytest.mark.parametrize(
    "snippet",
    [
        "db.execute(select(Product).where(Product.id == product_id))",
        "db.execute(update(Sale).values(status='completed'))",
        "db.scalars(select(Store))",
        'pdf.text(10, 20, "Invoice")',
        'cursor.execute("PRAGMA foreign_keys=ON")  # raw-sql: allowed (driver setting)',
    ],
)
def test_detector_allows_orm_and_marked_lines(snippet: str) -> None:
    assert not raw_sql_calls(snippet), snippet
