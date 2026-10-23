from sqlalchemy.exc import DBAPIError, OperationalError, ProgrammingError

# Postgres SQLSTATE for a missing column / table: the code is newer than the database schema.
_SCHEMA_SQLSTATES = {"42703", "42P01"}
_SCHEMA_MESSAGES = ("no such column", "no such table", "does not exist")


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def field_conflict(message: str, **fields: str) -> ApiError:
    """409 whose `details.fields` map each rejected input to the text shown under it."""
    return ApiError(409, "conflict", message, details={"fields": fields})


def unhandled_error(exc: Exception, *, debug: bool) -> tuple[int, dict[str, object]]:
    """Status and `{"error": ...}` body for an exception no handler caught. `debug` adds the exception text."""
    if isinstance(exc, ProgrammingError) and (
        getattr(exc.orig, "sqlstate", None) in _SCHEMA_SQLSTATES
        or any(text in str(exc.orig).lower() for text in _SCHEMA_MESSAGES)
    ):
        status, code = 500, "database_outdated"
        message = "The database schema is older than the API. Run the database migrations, then retry."
    elif isinstance(exc, OperationalError) or (isinstance(exc, DBAPIError) and exc.connection_invalidated):
        status, code = 503, "database_unavailable"
        message = "The API cannot reach its database. Check that PostgreSQL is running, then retry."
    else:
        status, code = 500, "internal_error"
        message = "The server hit an unexpected error. Retry, and contact support if it keeps happening."
    body: dict[str, object] = {"code": code, "message": message}
    if debug:
        detail = str(exc.orig if isinstance(exc, DBAPIError) and exc.orig is not None else exc)
        body["details"] = {"exception": type(exc).__name__, "detail": detail.splitlines()[0] if detail else ""}
    return status, {"error": body}


class SyncRejected(Exception):
    """A single sync event failed. The surrounding batch is rolled back."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
