"""Laundry price quotes. Tax uses the existing line tax helper. Rates are never invented here."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.tax import TAX_CATEGORIES, div_half_up, line_tax

UNITS = ("PIECE", "KG", "BAG", "LOAD", "SET", "PAIR", "METER", "SQUARE_METER", "HOUR")
MEASURED = frozenset({"KG", "METER", "SQUARE_METER", "HOUR"})


class LaundryPriceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class PriceQuote:
    unit: str
    quantity: int
    unit_price_cents: int
    extras_cents: int
    surcharge_cents: int
    discount_cents: int
    merchandise_cents: int
    minimum_charge_applied: bool
    tax_category: str
    rate_bps: int
    net_cents: int
    tax_cents: int
    total_cents: int


def net_weight(gross: int, tare: int) -> int:
    """Measured units in the service scale. Net weight is gross minus tare."""
    if gross < 0 or tare < 0:
        raise LaundryPriceError("invalid_quantity", "Weight cannot be negative.")
    if gross <= tare:
        raise LaundryPriceError("invalid_quantity", "Net weight must be greater than zero.")
    return gross - tare


def quote(
    *,
    unit: str,
    quantity: int,
    precision: int,
    unit_price_cents: int,
    min_charge_cents: int,
    min_quantity: int,
    extras_cents: int,
    express: bool,
    express_surcharge_cents: int | None,
    same_day: bool,
    same_day_surcharge_cents: int | None,
    special: bool,
    special_surcharge_cents: int | None,
    discount_cents: int,
    discount_authorized: bool,
    allow_zero_rate: bool,
    tax_category: str,
    rate_bps: int,
    price_includes_tax: bool,
) -> PriceQuote:
    """Quantity is a whole count, or measured units in the service precision (1250 at precision 3 is 1.250)."""
    if unit not in UNITS:
        raise LaundryPriceError("invalid_unit", "This pricing unit is not supported.")
    if precision < 0 or precision > 3:
        raise LaundryPriceError("invalid_precision", "Weight precision must be from 0 to 3.")
    if quantity <= 0:
        raise LaundryPriceError("invalid_quantity", "Quantity and weight must be greater than zero.")
    if min_quantity < 0 or extras_cents < 0 or discount_cents < 0 or min_charge_cents < 0:
        raise LaundryPriceError("invalid_amount", "Charges, extras, and discounts cannot be negative.")
    if unit_price_cents < 0 or (unit_price_cents == 0 and not allow_zero_rate):
        raise LaundryPriceError("invalid_rate", "The unit rate must be greater than zero.")
    if min_quantity and quantity < min_quantity:
        raise LaundryPriceError("below_minimum", "This service has a minimum quantity or weight.")
    if tax_category not in TAX_CATEGORIES:
        raise LaundryPriceError("invalid_tax", "The tax category is not one this business uses.")
    if rate_bps < 0:
        raise LaundryPriceError("invalid_tax", "The tax rate cannot be negative.")

    divisor = 10**precision if unit in MEASURED else 1
    merchandise = unit_price_cents * quantity if divisor == 1 else div_half_up(unit_price_cents * quantity, divisor)
    minimum_applied = False
    if merchandise < min_charge_cents:
        merchandise = min_charge_cents
        minimum_applied = True
    surcharge = _surcharge(express, express_surcharge_cents, "Express")
    surcharge += _surcharge(same_day, same_day_surcharge_cents, "Same-day")
    surcharge += _surcharge(special, special_surcharge_cents, "Special handling")
    before_discount = merchandise + extras_cents + surcharge
    if discount_cents and not discount_authorized:
        raise LaundryPriceError("discount_unauthorized", "This discount needs an authorized approval.")
    if discount_cents > before_discount:
        raise LaundryPriceError("invalid_discount", "The discount cannot be larger than the charge.")
    taxable = before_discount - discount_cents
    taxed = line_tax(taxable, 1, rate_bps, inclusive=price_includes_tax)
    return PriceQuote(
        unit=unit,
        quantity=quantity,
        unit_price_cents=unit_price_cents,
        extras_cents=extras_cents,
        surcharge_cents=surcharge,
        discount_cents=discount_cents,
        merchandise_cents=merchandise,
        minimum_charge_applied=minimum_applied,
        tax_category=tax_category,
        rate_bps=rate_bps,
        net_cents=taxed.net_cents,
        tax_cents=taxed.tax_cents,
        total_cents=taxed.line_total_cents,
    )


def _surcharge(selected: bool, amount: int | None, label: str) -> int:
    if not selected:
        return 0
    if amount is None:
        raise LaundryPriceError("surcharge_unavailable", f"{label} is not offered for this service.")
    if amount < 0:
        raise LaundryPriceError("invalid_amount", f"{label} surcharge cannot be negative.")
    return amount
