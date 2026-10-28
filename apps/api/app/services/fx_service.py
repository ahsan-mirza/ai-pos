"""Foreign cash: accepted currencies, exchange rates (manual or synced daily), and tender validation.

Informational conversion uses the same provider. It never rewrites prices or sales.
"""

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import cache
from app.core.config import Settings
from app.core.currency import SUPPORTED_CURRENCIES
from app.core.errors import ApiError, SyncRejected
from app.models.currency import AcceptedCurrency, ExchangeRate
from app.schemas.currencies import ConvertResult, CurrencyOut, CurrencyWrite, RateBoard, RateQuote, RateWrite
from app.schemas.payloads import SaleTenderPayload
from app.services.settings_service import business_currency
from app.tenancy.context import current_tenant

log = logging.getLogger("ai_pos.fx")
PROVIDER_NAME = "open.er-api.com"
RATE_QUANT = Decimal("0.00000001")
_MAX_CENTS = 10**14
_memory: dict[str, tuple[float, str]] = {}
_fetch_lock = threading.Lock()

NAMES = {
    "USD": "US dollar",
    "EUR": "Euro",
    "GBP": "Pound sterling",
    "SAR": "Saudi riyal",
    "INR": "Indian rupee",
    "PKR": "Pakistani rupee",
    "QAR": "Qatari riyal",
    "OMR": "Omani rial",
    "KWD": "Kuwaiti dinar",
    "BHD": "Bahraini dinar",
    "PHP": "Philippine peso",
    "CNY": "Chinese yuan",
    "RUB": "Russian ruble",
    "AED": "UAE dirham",
}


def latest_rate(db: Session, code: str) -> ExchangeRate | None:
    return db.scalar(
        select(ExchangeRate).where(ExchangeRate.currency == code).order_by(ExchangeRate.effective_at.desc()).limit(1)
    )


def list_currencies(db: Session) -> list[CurrencyOut]:
    base = business_currency(db)
    out = []
    for row in db.scalars(select(AcceptedCurrency).order_by(AcceptedCurrency.code)):
        rate = latest_rate(db, row.code)
        valid = rate is not None and rate.base_currency == base
        out.append(
            CurrencyOut(
                code=row.code,
                name=row.name,
                is_active=row.is_active,
                base_currency=base,
                rate_micros=rate.rate_micros if valid and rate else None,
                source=rate.source if valid and rate else None,
                effective_at=(rate.effective_at if rate.effective_at.tzinfo else rate.effective_at.replace(tzinfo=UTC))
                if valid and rate
                else None,
            )
        )
    return out


def save_currency(db: Session, data: CurrencyWrite) -> list[CurrencyOut]:
    code = data.code.upper()
    if code == business_currency(db):
        raise ApiError(422, "validation_error", f"{code} is the business currency already.")
    row = db.scalar(select(AcceptedCurrency).where(AcceptedCurrency.code == code))
    if row is None:
        row = AcceptedCurrency(code=code, name=data.name or NAMES.get(code, code))
        db.add(row)
    elif data.name:
        row.name = data.name
    row.is_active = data.is_active
    db.flush()
    if data.rate_micros is not None:
        db.add(
            ExchangeRate(
                currency=code, base_currency=business_currency(db), rate_micros=data.rate_micros, source="manual"
            )
        )
    db.commit()
    return list_currencies(db)


def set_rate(db: Session, code: str, data: RateWrite, user_id: uuid.UUID | None) -> list[CurrencyOut]:
    if db.scalar(select(AcceptedCurrency).where(AcceptedCurrency.code == code.upper())) is None:
        raise ApiError(404, "not_found", "Add the currency first.")
    db.add(
        ExchangeRate(
            currency=code.upper(),
            base_currency=business_currency(db),
            rate_micros=data.rate_micros,
            source="manual",
            created_by_id=user_id,
        )
    )
    db.commit()
    return list_currencies(db)


def sync_rates(db: Session, settings: Settings, fetch=None) -> int:
    """Refreshes every active currency from the configured provider. `fetch` is injectable for tests."""
    if settings.fx_provider == "manual" and fetch is None:
        return 0
    base = business_currency(db)
    if fetch is None:
        response = httpx.get(f"https://open.er-api.com/v6/latest/{base}", timeout=15)
        response.raise_for_status()
        rates = response.json().get("rates", {})
    else:
        rates = fetch(base)
    updated = 0
    for row in db.scalars(select(AcceptedCurrency).where(AcceptedCurrency.is_active.is_(True))):
        per_base = rates.get(row.code)
        if not per_base:
            continue
        db.add(
            ExchangeRate(
                currency=row.code,
                base_currency=base,
                rate_micros=round(1_000_000 / float(per_base)),
                source=settings.fx_provider if fetch is None else "sync",
                effective_at=datetime.now(UTC),
            )
        )
        updated += 1
    db.commit()
    return updated


def check_tender(db: Session, settings: Settings, tender: SaleTenderPayload, sale_currency: str) -> None:
    """Foreign cash must use an accepted currency at a rate close to the latest, and add up in the business currency."""
    if tender.currency is None or tender.currency.upper() == sale_currency:
        return
    code = tender.currency.upper()
    if tender.method != "cash":
        raise SyncRejected("Only cash can be taken in a foreign currency.")
    accepted = db.scalar(select(AcceptedCurrency).where(AcceptedCurrency.code == code))
    if accepted is None or not accepted.is_active:
        raise SyncRejected(f"{code} is not an accepted currency.")
    latest = latest_rate(db, code)
    if latest is None or latest.base_currency != sale_currency:
        raise SyncRejected(f"No {code} exchange rate is set.")
    assert tender.rate_micros is not None and tender.foreign_amount_cents is not None
    drift = abs(tender.rate_micros - latest.rate_micros) * 10_000 / latest.rate_micros
    if drift > settings.fx_tolerance_bps:
        raise SyncRejected(f"The {code} rate used differs from the current rate by more than allowed.")
    value = tender.foreign_amount_cents * tender.rate_micros / 1_000_000
    applied = tender.amount_cents + (tender.change_cents or 0)
    if abs(value - applied) > max(1.0, tender.rate_micros / 1_000_000):
        raise SyncRejected(f"{code} received does not match the amount and change at the rate used.")


class ProviderError(Exception):
    """The exchange-rate provider failed. Callers fall back to a cached table or report it unavailable."""


class QuoteUnavailable(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class RateMeta:
    source_currency: str
    target_currency: str
    rate: Decimal
    as_of: datetime
    provider: str
    status: str


@dataclass(frozen=True)
class _Table:
    rates: dict[str, Decimal]
    as_of: datetime
    provider: str
    status: str


def _code(value: str) -> str:
    code = value.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise ApiError(422, "validation_error", f"Currency must be one of {', '.join(SUPPORTED_CURRENCIES)}.")
    return code


def _amount(cents: int) -> int:
    if cents < 0 or cents > _MAX_CENTS:
        raise ApiError(422, "validation_error", "Enter an amount of zero or more.")
    return cents


def _tenant_key() -> str:
    tenant = current_tenant()
    return tenant.id if tenant is not None else "local"


def _cache_get(key: str) -> str | None:
    found = cache.get_value(key)
    if found is not None:
        return found
    item = _memory.get(key)
    if item is None:
        return None
    expires, value = item
    if expires < time.monotonic():
        _memory.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: str, ttl: int) -> None:
    if ttl <= 0:
        return
    cache.set_value(key, value, ttl)
    _memory[key] = (time.monotonic() + ttl, value)


def _quantize_rate(value: Decimal) -> Decimal:
    if value <= 0:
        raise ProviderError("A rate must be greater than zero.")
    return value.quantize(RATE_QUANT, rounding=ROUND_HALF_EVEN)


def _normalize(source: str, raw: object) -> dict[str, Decimal]:
    if not isinstance(raw, dict):
        raise ProviderError("The exchange-rate provider returned no rates.")
    out: dict[str, Decimal] = {}
    for code, value in raw.items():
        target = str(code).upper()
        if target not in SUPPORTED_CURRENCIES or target == source:
            continue
        try:
            rate = Decimal(str(value))
        except Exception as exc:
            raise ProviderError("The exchange-rate provider returned a rate that is not a number.") from exc
        if rate > 0:
            out[target] = _quantize_rate(rate)
    if not out:
        raise ProviderError("The exchange-rate provider returned none of the supported currencies.")
    return out


def _pull(settings: Settings, source: str) -> tuple[dict[str, Decimal], datetime]:
    """Live table from the configured provider. Credentials never leave this process."""
    url = f"{settings.fx_api_url.rstrip('/')}/{source}"
    headers: dict[str, str] = {}
    if settings.fx_api_key:
        headers["Authorization"] = f"Bearer {settings.fx_api_key}"
    try:
        response = httpx.get(url, headers=headers, timeout=httpx.Timeout(8.0, connect=3.0))
    except httpx.HTTPError as exc:
        raise ProviderError("The exchange-rate provider did not respond.") from exc
    if response.status_code == 429:
        raise ProviderError("The exchange-rate provider is rate limiting requests.")
    if response.status_code >= 400:
        raise ProviderError("The exchange-rate provider rejected the request.")
    try:
        body = json.loads(response.text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ProviderError("The exchange-rate provider returned an unreadable response.") from exc
    if not isinstance(body, dict):
        raise ProviderError("The exchange-rate provider returned an unreadable response.")
    result = body.get("result")
    if result not in (None, "success"):
        raise ProviderError("The exchange-rate provider rejected the request.")
    base = str(body.get("base_code") or body.get("base") or source).upper()
    if base != source:
        raise ProviderError("The exchange-rate provider returned a different base currency.")
    unix = body.get("time_last_update_unix")
    if isinstance(unix, (int, float)) and not isinstance(unix, bool):
        as_of = datetime.fromtimestamp(int(unix), UTC)
    else:
        as_of = datetime.now(UTC)
    return _normalize(source, body.get("rates")), as_of


def _decode(raw: str) -> _Table | None:
    try:
        body = json.loads(raw)
        rates = {code: Decimal(value) for code, value in body["rates"].items()}
        as_of = datetime.fromisoformat(body["as_of"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)
    return _Table(rates=rates, as_of=as_of, provider=str(body.get("provider") or PROVIDER_NAME), status="cached")


def _encode(source: str, rates: dict[str, Decimal], as_of: datetime) -> str:
    return json.dumps(
        {
            "source": source,
            "provider": PROVIDER_NAME,
            "as_of": as_of.isoformat(),
            "rates": {code: format(rate, "f") for code, rate in rates.items()},
        }
    )


def _table(
    settings: Settings,
    source: str,
    *,
    refresh: bool,
    fetch,
    fresh_ttl: int | None,
    stale_ttl: int | None,
) -> _Table:
    fresh_key = f"fx:v1:{source}"
    stale_key = f"fx:v1:stale:{source}"
    fresh_for = settings.fx_quote_ttl_seconds if fresh_ttl is None else fresh_ttl
    stale_for = max(settings.fx_quote_stale_seconds if stale_ttl is None else stale_ttl, fresh_for)
    if refresh and not cache.try_claim(f"fx-refresh:{_tenant_key()}:{source}", settings.fx_refresh_seconds):
        cached = _decode(_cache_get(fresh_key) or "") or _decode(_cache_get(stale_key) or "")
        if cached is None:
            raise QuoteUnavailable("Rates were refreshed recently, and no saved rate is available yet.")
        log.info("fx quote source=%s status=cached provider=%s", source, cached.provider)
        return cached
    if not refresh:
        fresh = _decode(_cache_get(fresh_key) or "")
        if fresh is not None:
            return _Table(fresh.rates, fresh.as_of, fresh.provider, "live")
    try:
        with _fetch_lock:
            if not refresh:
                fresh = _decode(_cache_get(fresh_key) or "")
                if fresh is not None:
                    return _Table(fresh.rates, fresh.as_of, fresh.provider, "live")
            if fetch is not None:
                pulled = fetch(source)
                if isinstance(pulled, tuple):
                    rates, as_of = _normalize(source, pulled[0]), pulled[1]
                else:
                    rates, as_of = _normalize(source, pulled), datetime.now(UTC)
            else:
                rates, as_of = _pull(settings, source)
    except (ProviderError, QuoteUnavailable) as exc:
        cached = _decode(_cache_get(stale_key) or "") or _decode(_cache_get(fresh_key) or "")
        if cached is None:
            log.info("fx quote source=%s status=unavailable", source)
            raise QuoteUnavailable("Exchange rates are unavailable. No saved rate can be used.") from exc
        log.info("fx quote source=%s status=cached provider=%s", source, cached.provider)
        return cached
    payload = _encode(source, rates, as_of)
    _cache_set(fresh_key, payload, fresh_for)
    _cache_set(stale_key, payload, stale_for)
    log.info("fx quote source=%s status=live provider=%s", source, PROVIDER_NAME)
    return _Table(rates, as_of, PROVIDER_NAME, "live")


def _inverse(rate: Decimal) -> Decimal:
    return (Decimal(1) / rate).quantize(RATE_QUANT, rounding=ROUND_HALF_EVEN)


def _converted(amount_cents: int, rate: Decimal) -> int:
    return int((Decimal(amount_cents) * rate).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def get_exchange_rate(
    source_currency: str,
    target_currency: str,
    settings: Settings,
    *,
    refresh: bool = False,
    fetch=None,
    fresh_ttl: int | None = None,
    stale_ttl: int | None = None,
) -> RateMeta:
    """Target units for one source unit. The inverse of a cached pair uses that same rate."""
    source = _code(source_currency)
    target = _code(target_currency)
    if source == target:
        return RateMeta(source, target, Decimal(1), datetime.now(UTC), "identity", "live")
    table: _Table | None
    try:
        table = _table(settings, source, refresh=refresh, fetch=fetch, fresh_ttl=fresh_ttl, stale_ttl=stale_ttl)
    except QuoteUnavailable:
        table = None
    if table is not None and target in table.rates:
        return RateMeta(source, target, table.rates[target], table.as_of, table.provider, table.status)
    try:
        other = _table(settings, target, refresh=False, fetch=fetch, fresh_ttl=fresh_ttl, stale_ttl=stale_ttl)
    except QuoteUnavailable as exc:
        raise QuoteUnavailable(f"No {source} to {target} rate is available.") from exc
    opposite = other.rates.get(source)
    if opposite is None:
        raise QuoteUnavailable(f"No {source} to {target} rate is available.")
    return RateMeta(source, target, _inverse(opposite), other.as_of, other.provider, other.status)


def get_rate_metadata(source_currency: str, target_currency: str, settings: Settings, **kwargs) -> RateMeta:
    return get_exchange_rate(source_currency, target_currency, settings, **kwargs)


def convert_amount(
    amount_cents: int,
    source_currency: str,
    target_currency: str,
    settings: Settings,
    **kwargs,
) -> tuple[int, RateMeta]:
    meta = get_exchange_rate(source_currency, target_currency, settings, **kwargs)
    return _converted(_amount(amount_cents), meta.rate), meta


def _result(amount_cents: int, meta: RateMeta) -> ConvertResult:
    return ConvertResult(
        source_currency=meta.source_currency,
        target_currency=meta.target_currency,
        amount_cents=amount_cents,
        converted_cents=_converted(amount_cents, meta.rate),
        rate=format(meta.rate, "f"),
        inverse_rate=format(_inverse(meta.rate) if meta.rate != 1 else Decimal(1), "f"),
        as_of=meta.as_of,
        provider=meta.provider,
        status="cached" if meta.status == "cached" else "live",
    )


def convert(
    amount_cents: int, source_currency: str, target_currency: str, settings: Settings, **kwargs
) -> ConvertResult:
    cents, meta = convert_amount(_amount(amount_cents), source_currency, target_currency, settings, **kwargs)
    # convert_amount already rounded; rebuild from the same meta so the returned cents match.
    result = _result(amount_cents, meta)
    if result.converted_cents != cents:
        result = result.model_copy(update={"converted_cents": cents})
    return result


def rate_board(
    settings: Settings,
    source_currency: str,
    amount_cents: int,
    *,
    refresh: bool = False,
    fetch=None,
    fresh_ttl: int | None = None,
    stale_ttl: int | None = None,
) -> RateBoard:
    source = _code(source_currency)
    amount = _amount(amount_cents)
    try:
        table = _table(settings, source, refresh=refresh, fetch=fetch, fresh_ttl=fresh_ttl, stale_ttl=stale_ttl)
    except QuoteUnavailable as exc:
        return RateBoard(
            source_currency=source,
            amount_cents=amount,
            provider=PROVIDER_NAME,
            as_of=None,
            status="unavailable",
            message=exc.message,
            quotes=[
                RateQuote(
                    currency=code,
                    rate="1" if code == source else None,
                    inverse_rate="1" if code == source else None,
                    converted_cents=amount if code == source else None,
                    status="same" if code == source else "unavailable",
                )
                for code in SUPPORTED_CURRENCIES
            ],
        )
    quotes: list[RateQuote] = []
    for code in SUPPORTED_CURRENCIES:
        if code == source:
            quotes.append(RateQuote(currency=code, rate="1", inverse_rate="1", converted_cents=amount, status="same"))
            continue
        rate = table.rates.get(code)
        if rate is None:
            quotes.append(
                RateQuote(currency=code, rate=None, inverse_rate=None, converted_cents=None, status="unavailable")
            )
            continue
        quotes.append(
            RateQuote(
                currency=code,
                rate=format(rate, "f"),
                inverse_rate=format(_inverse(rate), "f"),
                converted_cents=_converted(amount, rate),
                status="cached" if table.status == "cached" else "live",
            )
        )
    unavailable = [quote for quote in quotes if quote.status == "unavailable"]
    message = None
    if table.status == "cached":
        message = "Showing a saved rate. The provider did not return a newer one."
    elif unavailable:
        message = "Some currencies have no rate from the provider."
    return RateBoard(
        source_currency=source,
        amount_cents=amount,
        provider=table.provider,
        as_of=table.as_of,
        status="cached" if table.status == "cached" else "live",
        message=message,
        quotes=quotes,
    )
