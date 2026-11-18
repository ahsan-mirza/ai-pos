"""Marketing origins stay explicit, and logs do not keep credentials."""

import logging

from app.main import _RedactSecrets


def test_marketing_origin_is_allowed(client) -> None:
    response = client.options(
        "/api/v1/demo-access/exchange",
        headers={"Origin": "https://axizpos.com", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") == "https://axizpos.com"


def test_unknown_origin_is_refused(client) -> None:
    response = client.options(
        "/api/v1/demo-access/exchange",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_log_filter_redacts_tokens_and_bearer_headers() -> None:
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, "GET %s", ("/live?token=secret-value",), None
    )
    assert _RedactSecrets().filter(record) is True
    rendered = record.getMessage()
    assert "secret-value" not in rendered
    assert "token=redacted" in rendered

    bearer = logging.LogRecord("ai_pos", logging.INFO, __file__, 1, "Authorization: Bearer abc.def", (), None)
    _RedactSecrets().filter(bearer)
    assert "abc.def" not in bearer.getMessage()
    assert "Bearer redacted" in bearer.getMessage()
