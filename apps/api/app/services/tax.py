"""VAT arithmetic. Mirrors packages/shared-types/src/tax.ts; both are checked against
packages/shared-types/fixtures/tax-cases.json. Rounding is half-up on whole cents per line."""

import uuid
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

TAX_CATEGORIES = ("STANDARD", "ZERO", "EXEMPT")
# Customer treatments that take standard-rated lines to 0%: exports, exempt bodies, designated-zone supplies.
RELIEVED_TREATMENTS = ("ZERO_EXPORT", "EXEMPT", "DESIGNATED_ZONE")


def div_half_up(numerator: int, denominator: int) -> int:
    """Integer division rounding halves away from zero (Python's round() is banker's rounding)."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if numerator < 0 else 1
    return sign * ((abs(numerator) * 2 + denominator) // (2 * denominator))


@dataclass(frozen=True)
class TaxPolicy:
    enforced: bool
    prices_include_vat: bool
    standard_rate_bps: int
    # The customer's treatment when it relieves standard-rated lines (see for_customer).
    treatment: str = "STANDARD"

    def rate_for(self, category: str) -> int:
        if category != "STANDARD" or self.treatment in RELIEVED_TREATMENTS:
            return 0
        return self.standard_rate_bps


def treatment_of(customer: Any, on: date) -> str:
    """The customer's VAT treatment on `on`: an expired certificate falls back to STANDARD."""
    if customer is None:
        return "STANDARD"
    treatment = getattr(customer, "tax_treatment", None) or "STANDARD"
    expiry = getattr(customer, "tax_certificate_expiry", None)
    if treatment != "STANDARD" and expiry is not None and expiry < on:
        return "STANDARD"
    return treatment


def for_customer(base: "TaxPolicy", customer: Any, on: date) -> "TaxPolicy":
    return replace(base, treatment=treatment_of(customer, on))


@dataclass(frozen=True)
class LineTax:
    net_cents: int
    tax_cents: int
    line_total_cents: int


def entered_includes_tax(product: Any) -> bool:
    """True when this product's entered selling price already contains tax.

    Missing on older rows means tax-exclusive. It does not follow the business-wide
    prices-include-VAT switch, so two products in one sale can differ.
    """
    return bool(getattr(product, "price_includes_tax", False))


def line_tax(unit_price_cents: int, quantity: int, rate_bps: int, *, inclusive: bool) -> LineTax:
    gross = unit_price_cents * quantity
    if inclusive:
        tax = div_half_up(gross * rate_bps, 10_000 + rate_bps)
        return LineTax(net_cents=gross - tax, tax_cents=tax, line_total_cents=gross)
    tax = div_half_up(gross * rate_bps, 10_000)
    return LineTax(net_cents=gross, tax_cents=tax, line_total_cents=gross + tax)


def policy(db: Session, store_id: uuid.UUID | None = None) -> TaxPolicy:
    """Business-wide tax, or the selling branch's own profile when that branch has one.

    A missing branch profile keeps the business settings. It never borrows another branch's profile.
    """
    if store_id is not None:
        from app.services.branch_tax import policy_for_store

        branch = policy_for_store(db, store_id)
        if branch is not None:
            return branch
    from app.services.settings_service import cached_settings

    row = cached_settings(db)
    return TaxPolicy(
        enforced=bool(row.vat_registered),
        prices_include_vat=bool(row.prices_include_vat),
        standard_rate_bps=int(row.standard_rate_bps),
    )
