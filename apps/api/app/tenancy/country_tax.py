"""Country tax and localization metadata.

Rates are included only where this product already bills against a verified rate
(UAE, Saudi Arabia, Bahrain, Oman). Every other country is configuration-required:
the business enters the rate. Nothing here is a complete legal ruleset.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CountryTax:
    code: str
    tax_name: str
    registration_label: str
    secondary_registration_label: str | None
    legal_local_language: str | None
    legal_local_label: str | None
    region_label: str | None
    rate_known: bool
    standard_rate_bps: int | None
    prices_include_vat: bool
    tax_authority: str
    categories: tuple[str, ...] = ("STANDARD", "ZERO", "EXEMPT")


_KNOWN: dict[str, CountryTax] = {
    "AE": CountryTax(
        "AE", "VAT", "TRN", None, "ar", "Legal name (Arabic)", "Emirate", True, 500, True, "fta"
    ),
    "SA": CountryTax(
        "SA",
        "VAT",
        "VAT registration number",
        None,
        "ar",
        "Legal name (Arabic)",
        None,
        True,
        1500,
        False,
        "zatca",
    ),
    "BH": CountryTax(
        "BH", "VAT", "VAT registration number", None, "ar", "Legal name (Arabic)", None, True, 1000, False, "fta"
    ),
    "OM": CountryTax(
        "OM", "VAT", "VAT registration number", None, "ar", "Legal name (Arabic)", None, True, 500, False, "fta"
    ),
    "PK": CountryTax(
        "PK",
        "Sales tax",
        "NTN",
        "Sales tax registration number (STRN)",
        "ur",
        "Legal name (Urdu)",
        "Province",
        False,
        None,
        False,
        "fta",
    ),
    "GB": CountryTax(
        "GB", "VAT", "VAT registration number", None, None, None, None, False, None, False, "fta"
    ),
    "US": CountryTax(
        "US", "Sales tax", "Sales tax registration", None, None, None, "State", False, None, False, "fta"
    ),
}


def describe(code: str) -> CountryTax:
    """Metadata for an ISO country. Unknown countries do not receive an invented rate."""
    key = code.upper()
    found = _KNOWN.get(key)
    if found is not None:
        return found
    return CountryTax(
        key,
        "Tax",
        "Tax registration number",
        None,
        None,
        None,
        None,
        False,
        None,
        False,
        "fta",
    )


def as_dict(row: CountryTax) -> dict[str, object]:
    return {
        "code": row.code,
        "tax_name": row.tax_name,
        "registration_label": row.registration_label,
        "secondary_registration_label": row.secondary_registration_label,
        "legal_local_language": row.legal_local_language,
        "legal_local_label": row.legal_local_label,
        "region_label": row.region_label,
        "rate_known": row.rate_known,
        "standard_rate_bps": row.standard_rate_bps,
        "prices_include_vat": row.prices_include_vat,
        "tax_authority": row.tax_authority,
        "categories": list(row.categories),
    }
