from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel


class CurrencyOut(ApiModel):
    code: str
    name: str
    is_active: bool
    base_currency: str
    # Business-currency units per one foreign unit, times 1,000,000.
    rate_micros: int | None
    source: str | None
    effective_at: datetime | None


class CurrencyWrite(ApiModel):
    code: str = Field(pattern=r"^[A-Za-z]{3}$")
    name: str | None = Field(default=None, max_length=60)
    is_active: bool = True
    rate_micros: int | None = Field(default=None, ge=1, le=10_000_000_000)


class RateWrite(ApiModel):
    rate_micros: int = Field(ge=1, le=10_000_000_000)


class RateQuote(ApiModel):
    """One currency beside the source. `rate` is target units for 1 source unit. Null means no rate was available."""

    currency: str
    rate: str | None
    inverse_rate: str | None
    converted_cents: int | None
    status: Literal["same", "live", "cached", "unavailable"]


class RateBoard(ApiModel):
    source_currency: str
    amount_cents: int
    provider: str
    as_of: datetime | None
    status: Literal["live", "cached", "unavailable"]
    message: str | None
    quotes: list[RateQuote]


class ConvertResult(ApiModel):
    source_currency: str
    target_currency: str
    amount_cents: int
    converted_cents: int
    rate: str
    inverse_rate: str
    as_of: datetime
    provider: str
    status: Literal["live", "cached"]
