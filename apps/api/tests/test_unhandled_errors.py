from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.errors import unhandled_error
from app.main import create_app

ORIGIN = "http://localhost:5173"


class _UndefinedColumn(Exception):
    sqlstate = "42703"


def _app_raising(exc: Exception):  # type: ignore[no-untyped-def]
    app = create_app()

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise exc

    return app


def test_crash_returns_json_with_cors_headers() -> None:
    client = TestClient(_app_raising(RuntimeError("kaboom")))
    response = client.get("/api/v1/boom", headers={"Origin": ORIGIN})
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ORIGIN
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["details"] == {"exception": "RuntimeError", "detail": "kaboom"}


def test_missing_column_reports_outdated_schema() -> None:
    exc = ProgrammingError("SELECT 1", {}, _UndefinedColumn("column business_settings.module_settings does not exist"))
    client = TestClient(_app_raising(exc))
    error = client.get("/api/v1/boom", headers={"Origin": ORIGIN}).json()["error"]
    assert error["code"] == "database_outdated"
    assert "migrations" in error["message"]


def test_database_down_is_503() -> None:
    status, body = unhandled_error(OperationalError("SELECT 1", {}, Exception("connection refused")), debug=False)
    assert status == 503
    assert body == {
        "error": {
            "code": "database_unavailable",
            "message": "The API cannot reach its database. Check that PostgreSQL is running, then retry.",
        }
    }
