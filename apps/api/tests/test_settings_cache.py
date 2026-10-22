import time

from sqlalchemy import event, update
from sqlalchemy.orm import Session

from app.models import BusinessSettings
from app.services import settings_service
from test_returns import admin_token, bearer, device


def settings_selects(session: Session):
    """Records SELECTs against business_settings issued on the session's engine."""
    engine = session.get_bind()
    seen: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "business_settings" in statement:
            seen.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    return seen, lambda: event.remove(engine, "before_cursor_execute", record)


def warm(client) -> None:
    for _ in range(2):
        assert client.get("/api/v1/settings", headers=device()).status_code == 200


def test_repeated_reads_are_served_from_cache(client, session: Session) -> None:
    warm(client)
    seen, stop = settings_selects(session)
    try:
        for _ in range(5):
            assert client.get("/api/v1/settings", headers=device()).json()["currency"] == "USD"
            assert settings_service.business_currency(session) == "USD"
    finally:
        stop()
    assert seen == []


def test_currency_change_is_visible_on_the_next_read(client) -> None:
    warm(client)
    changed = client.put("/api/v1/settings/currency", headers=bearer(admin_token(client)), json={"currency": "EUR"})
    assert changed.status_code == 200, changed.text
    assert client.get("/api/v1/settings", headers=device()).json()["currency"] == "EUR"


def test_any_committed_orm_write_invalidates(client, session: Session) -> None:
    warm(client)
    row = settings_service.load_settings(session)
    row.trn = "100000000000003"
    session.commit()
    assert settings_service.cached_settings(session).trn == "100000000000003"

    session.execute(update(BusinessSettings).values(currency="GBP"))
    session.commit()
    assert settings_service.business_currency(session) == "GBP"


def test_uncommitted_change_is_seen_only_by_its_own_session(client, session: Session) -> None:
    warm(client)
    row = settings_service.load_settings(session)
    row.currency = "SAR"
    assert settings_service.business_currency(session) == "SAR"
    session.rollback()
    assert settings_service.business_currency(session) == "USD"


def test_ttl_bounds_staleness_from_other_workers(client, session: Session, monkeypatch) -> None:
    warm(client)
    session.execute(update(BusinessSettings).values(currency="QAR"))
    session.info.pop(settings_service._CHANGED)  # as if another API process committed the change
    session.commit()
    assert settings_service.business_currency(session) == "USD"

    later = time.monotonic() + settings_service.CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(settings_service.time, "monotonic", lambda: later)
    assert settings_service.business_currency(session) == "QAR"


def test_cached_snapshot_is_read_only(client, session: Session) -> None:
    warm(client)
    snapshot = settings_service.cached_settings(session)
    try:
        snapshot.currency = "INR"  # type: ignore[misc]
    except AttributeError:
        pass
    assert settings_service.business_currency(session) == "USD"
