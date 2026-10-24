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
    assert error["api"] == "GET /api/v1/boom"
    assert error["details"] == {"exception": "RuntimeError", "detail": "kaboom"}


def test_missing_column_reports_outdated_schema() -> None:
    exc = ProgrammingError("SELECT 1", {}, _UndefinedColumn("column business_settings.module_settings does not exist"))
    client = TestClient(_app_raising(exc))
    error = client.get("/api/v1/boom", headers={"Origin": ORIGIN}).json()["error"]
    assert error["code"] == "database_outdated"
    assert error["api"] == "GET /api/v1/boom"
    assert "migrations" in error["message"]


def test_unknown_api_names_itself() -> None:
    client = TestClient(create_app())
    error = client.get("/api/v1/does-not-exist", headers={"Origin": ORIGIN}).json()["error"]
    assert error["code"] == "not_found"
    assert error["message"] == "That API does not exist."
    assert error["api"] == "GET /api/v1/does-not-exist"


def test_validation_error_names_the_field() -> None:
    from app.core.errors import validation_message

    message = validation_message(
        [
            {"loc": ["body", "password"], "msg": "Value error, Password needs an uppercase letter."},
            {"loc": ["body", "full_name"], "msg": "Field required"},
            {"loc": ["body", "password"], "msg": "String should have at least 10 characters"},
        ]
    )
    assert message == (
        "Password needs an uppercase letter. Full name is required. Password should have at least 10 characters."
    )


def test_database_down_is_503() -> None:
    status, body = unhandled_error(OperationalError("SELECT 1", {}, Exception("connection refused")), debug=False)
    assert status == 503
    assert body == {
        "error": {
            "code": "database_unavailable",
            "message": "The API cannot reach its database. Check that PostgreSQL is running, then retry.",
        }
    }
