import re

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


def api_name(method: str, path: str) -> str:
    """The API a client called, without the query string."""
    return f"{method.upper()} {path}"


def error_payload(
    code: str,
    message: str,
    *,
    api: str | None = None,
    details: object | None = None,
) -> dict[str, object]:
    """Every API error: a stable code, a sentence, and the API that failed."""
    error: dict[str, object] = {"code": code, "message": message}
    if api:
        error["api"] = api
    if details not in (None, {}, []):
        error["details"] = details
    return {"error": error}


_LOC_SKIP = {"body", "query", "path", "header", "cookie"}
_STOCK_TYPE = re.compile(
    r"^(?:string|input|value|list|tuple|set|bytes|decimal input|int|float|bool|datetime|date|time|uuid) ",
    re.IGNORECASE,
)


def _field_label(loc: object) -> str:
    parts = [str(part) for part in loc] if isinstance(loc, list | tuple) else []
    names = [part.replace("_", " ") for part in parts if part not in _LOC_SKIP and not part.isdigit()]
    label = names[-1] if names else "Request"
    return label[:1].upper() + label[1:]


def _validation_sentence(label: str, raw: str, kind: str = "") -> str:
    text = raw.removeprefix("Value error, ").strip().rstrip(".")
    lowered = text.lower()
    if kind == "extra_forbidden" or lowered == "extra inputs are not permitted":
        return f"{label} cannot be changed here."
    if lowered == "field required":
        return f"{label} is required."
    stock = _STOCK_TYPE.match(text)
    if stock and text[stock.end() :].lower().startswith("should"):
        rest = text[stock.end() :]
        return f"{label} {rest[0].lower()}{rest[1:]}."
    return text if text.endswith(".") else f"{text}."


def validation_message(errors: list[object]) -> str:
    """One readable sentence per invalid field, in the order the request was checked."""
    sentences: list[str] = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        sentence = _validation_sentence(
            _field_label(item.get("loc")),
            str(item.get("msg") or "Check this value."),
            str(item.get("type") or ""),
        )
        if sentence not in sentences:
            sentences.append(sentence)
    return " ".join(sentences) if sentences else "The request is missing or invalid."


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media",
    422: "invalid_request",
    429: "too_many_requests",
}
_HTTP_MESSAGES = {
    401: "Sign in again to continue.",
    403: "You do not have access to this.",
    404: "That API does not exist.",
    405: "That API does not accept this method.",
}
_STOCK_DETAILS = {"not found", "method not allowed", "unauthorized", "forbidden", "bad request"}


def http_error(status: int, detail: object) -> tuple[str, str]:
    """Code and message for an HTTP failure that did not raise ApiError."""
    code = _HTTP_CODES.get(status, "http_error")
    if isinstance(detail, str):
        text = detail.strip()
        if text and text.lower() not in _STOCK_DETAILS:
            return code, text if text.endswith(".") else f"{text}."
    return code, _HTTP_MESSAGES.get(status, "The request could not be completed.")


def unhandled_error(exc: Exception, *, debug: bool, api: str | None = None) -> tuple[int, dict[str, object]]:
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
    details = None
    if debug:
        detail = str(exc.orig if isinstance(exc, DBAPIError) and exc.orig is not None else exc)
        details = {"exception": type(exc).__name__, "detail": detail.splitlines()[0] if detail else ""}
    return status, error_payload(code, message, api=api, details=details)


class SyncRejected(Exception):
    """A single sync event failed. The surrounding batch is rolled back."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
