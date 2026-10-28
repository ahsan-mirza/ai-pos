from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import get_settings
from app.models import Product, Sale
from app.services import fx_service
from app.services.fx_service import ProviderError, QuoteUnavailable
from test_returns import CABLE_ID, admin_token, device, record_sale, seed_catalog
from test_settings import bearer, change_currency


def _clear() -> None:
    fx_service._memory.clear()


def test_conversion_uses_the_provider_rate_and_its_inverse(client) -> None:
    _clear()
    settings = get_settings()

    def fetch(source: str):
        if source == "AED":
            return {"PKR": Decimal("4"), "USD": Decimal("0.5")}
        raise ProviderError("down")

    converted, meta = fx_service.convert_amount(10_000, "AED", "PKR", settings, fetch=fetch)
    assert converted == 40_000
    assert meta.status == "live"
    assert meta.rate == Decimal("4.00000000")
    back, inverse = fx_service.convert_amount(converted, "PKR", "AED", settings, fetch=fetch)
    assert inverse.rate == Decimal("0.25000000")
    assert back == 10_000
    half, _ = fx_service.convert_amount(1, "AED", "USD", settings, fetch=fetch)
    assert half == 1
    _clear()
    cache.delete("fx:v1:AED")
    cache.delete("fx:v1:stale:AED")
    down, _ = fx_service.convert_amount(
        1, "AED", "USD", settings, fetch=lambda _source: {"USD": Decimal("0.4")}, fresh_ttl=0
    )
    assert down == 0


def test_a_provider_failure_uses_the_saved_rate_and_never_invents_one(client) -> None:
    _clear()
    settings = get_settings()
    calls = {"n": 0}

    def fetch(_source: str):
        calls["n"] += 1
        if calls["n"] > 1:
            raise ProviderError("timeout")
        return {"PKR": Decimal("10")}

    board = fx_service.rate_board(settings, "AED", 129_950, fetch=fetch, fresh_ttl=0, stale_ttl=60)
    assert board.status == "live"
    same = next(quote for quote in board.quotes if quote.currency == "AED")
    assert same.status == "same" and same.converted_cents == 129_950
    pkr = next(quote for quote in board.quotes if quote.currency == "PKR")
    assert pkr.converted_cents == 1_299_500
    again = fx_service.rate_board(settings, "AED", 129_950, fetch=fetch, fresh_ttl=0, stale_ttl=60)
    assert again.status == "cached"
    saved = next(quote for quote in again.quotes if quote.currency == "PKR")
    assert saved.converted_cents == 1_299_500

    _clear()
    cache.delete("fx:v1:AED")
    cache.delete("fx:v1:stale:AED")

    def down(_source: str):
        raise ProviderError("down")

    try:
        fx_service.get_exchange_rate("AED", "PKR", settings, fetch=down)
    except QuoteUnavailable as exc:
        assert "no aed to pkr rate" in exc.message.lower()
    else:
        raise AssertionError("missing rate")


def test_exchange_rate_routes_require_auth_and_known_currencies(client) -> None:
    _clear()
    assert client.get("/api/v1/settings/exchange-rates?source=AED&amount_cents=100").status_code == 401
    denied = client.get(
        "/api/v1/settings/exchange-rates?source=ZZZ&amount_cents=100",
        headers=device(),
    )
    assert denied.status_code == 422

    def fetch(_source: str):
        return {
            "PKR": Decimal("76.5"),
            "USD": Decimal("0.27"),
            "EUR": Decimal("0.25"),
            "GBP": Decimal("0.21"),
            "SAR": Decimal("1.02"),
            "QAR": Decimal("0.99"),
            "INR": Decimal("22"),
            "CNY": Decimal("1.9"),
        }

    original = fx_service._pull
    fx_service._pull = lambda _settings, source: (fetch(source), datetime.now(UTC))
    try:
        live = client.get(
            "/api/v1/settings/exchange-rates/convert?source=AED&target=PKR&amount_cents=129950",
            headers=device(),
        )
        assert live.status_code == 200, live.text
        assert live.json()["converted_cents"] == 9_941_175
        assert live.json()["status"] == "live"
        same = client.get(
            "/api/v1/settings/exchange-rates/convert?source=AED&target=AED&amount_cents=129950",
            headers=device(),
        )
        assert same.status_code == 200
        assert same.json()["converted_cents"] == 129950
        limited = client.get(
            "/api/v1/settings/exchange-rates?source=AED&amount_cents=100&refresh=true",
            headers=device(),
        )
        assert limited.status_code == 200
        again = client.get(
            "/api/v1/settings/exchange-rates?source=AED&amount_cents=100&refresh=true",
            headers=device(),
        )
        assert again.status_code == 200
        assert again.json()["status"] == "cached"
    finally:
        fx_service._pull = original


def test_pending_offline_sales_block_a_currency_change(client, session: Session) -> None:
    seed_catalog(client)
    record_sale(client, product_id=CABLE_ID, price=1500)
    token = admin_token(client)
    assert client.get("/api/v1/settings", headers={**device(), "X-Pending-Sales": "2"}).status_code == 200
    denied = change_currency(client, token, "AED")
    assert denied.status_code == 409
    assert "unsynced" in denied.json()["error"]["message"]
    assert client.get("/api/v1/settings", headers=bearer(token)).json()["currency"] == "USD"

    assert client.get("/api/v1/settings", headers={**device(), "X-Pending-Sales": "0"}).status_code == 200
    changed = change_currency(client, token, "AED")
    assert changed.status_code == 200, changed.text
    session.expire_all()
    sale = session.scalars(select(Sale)).one()
    assert sale.currency == "USD"
    assert sale.total_cents == 1500 + round(1500 * 500 / 10_000)
    product = session.get(Product, UUID(CABLE_ID))
    assert product is not None
    assert product.currency == "AED"
    assert product.price_cents == 1500
