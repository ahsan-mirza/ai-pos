"""Foreign cash: accepted currencies, exchange rates (manual or synced daily), and tender validation."""

import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError, SyncRejected
from app.models.currency import AcceptedCurrency, ExchangeRate
from app.schemas.currencies import CurrencyOut, CurrencyWrite, RateWrite
from app.schemas.payloads import SaleTenderPayload
from app.services.settings_service import business_currency

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
    row = db.get(AcceptedCurrency, code)
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
    if db.get(AcceptedCurrency, code.upper()) is None:
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
    accepted = db.get(AcceptedCurrency, code)
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
