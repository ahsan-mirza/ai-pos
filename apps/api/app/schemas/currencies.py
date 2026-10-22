from datetime import datetime

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
