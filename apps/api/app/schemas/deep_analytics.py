"""Deep Analytics responses. Money is fils. A missing figure stays null instead of becoming zero."""

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel

Quality = Literal["exact", "estimated", "unavailable"]


class Kpi(ApiModel):
    key: str
    label: str
    definition: str
    formula: str
    cents: int | None = None
    count: int | None = None
    bps: int | None = None
    quality: Quality
    note: str | None = None


class TrendPoint(ApiModel):
    day: date
    revenue_cents: int
    gross_profit_cents: int


class HourPoint(ApiModel):
    hour: int
    revenue_cents: int


class NamedAmount(ApiModel):
    name: str
    cents: int


class AnalyticsSection(ApiModel):
    id: str
    label: str
    status: Literal["available", "unavailable"]
    detail: str
    cents: int | None = None


class ForecastOut(ApiModel):
    status: Literal["insufficient_history", "estimated"]
    horizon_days: int = 7
    method: str
    daily_revenue_cents: int | None = None
    note: str


class Comparison(ApiModel):
    period_from: date
    period_to: date
    revenue_cents: int
    gross_profit_cents: int
    transactions: int
    revenue_growth_bps: int | None = None
    profit_growth_bps: int | None = None


class DeepOverview(ApiModel):
    currency: str
    period_from: date
    period_to: date
    generated_at: datetime
    # Posted sales already in the store database. A register that has not synced is not included.
    coverage: str
    cost_estimated: bool
    kpis: list[Kpi]
    comparison: Comparison | None = None
    trend: list[TrendPoint]
    hourly: list[HourPoint]
    hourly_note: str | None = None
    categories: list[NamedAmount]
    products: list[NamedAmount] = Field(default_factory=list)
    slow_products: list[NamedAmount] = Field(default_factory=list)
    payments: list[NamedAmount]
    cashiers: list[NamedAmount] = Field(default_factory=list)
    branches: list[NamedAmount] = Field(default_factory=list)
    payments_note: str = (
        "Payment totals are the amount tendered, including VAT, before refunds. They are not net sales."
    )
    sections: list[AnalyticsSection]
    forecast: ForecastOut
