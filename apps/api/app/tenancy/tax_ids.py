"""Country-specific tax and business registration numbers for signup.

Only formats the product already treats as established are checked strictly: a UAE TRN,
a Saudi VAT number, a UK VAT number, and a US EIN. Every other country accepts a short
registration identifier or a blank value when the business is not tax-registered.
"""

from __future__ import annotations

import re

_LOOSE = re.compile(r"^[A-Z0-9](?:[A-Z0-9 \-]{0,30}[A-Z0-9])?$")


class TaxIdError(ValueError):
    """The number does not match the selected country's known format."""


def normalize_tax_id(country: str, value: str | None) -> str | None:
    """Return the stored identifier, or None when the business left it blank."""
    if value is None:
        return None
    cleaned = re.sub(r"\s+", " ", value).strip().upper()
    if cleaned == "":
        return None
    iso = country.strip().upper()
    if iso == "AE":
        digits = re.sub(r"\D", "", cleaned)
        if not re.fullmatch(r"\d{15}", digits):
            raise TaxIdError("A UAE TRN is 15 digits. Leave it blank if the business is not VAT-registered.")
        return digits
    if iso == "SA":
        digits = re.sub(r"\D", "", cleaned)
        if not (len(digits) == 15 and digits.startswith("3") and digits.endswith("3")):
            raise TaxIdError(
                "A Saudi VAT number is 15 digits that start and end with 3. "
                "Leave it blank if the business is not VAT-registered."
            )
        return digits
    if iso == "GB":
        compact = cleaned.replace(" ", "")
        if not re.fullmatch(r"(?:GB)?\d{9}(?:\d{3})?", compact):
            raise TaxIdError(
                "A UK VAT number is 9 digits, optionally starting with GB. "
                "Leave it blank if the business is not VAT-registered."
            )
        return compact if compact.startswith("GB") else f"GB{compact}"
    if iso == "US":
        digits = re.sub(r"\D", "", cleaned)
        if len(digits) != 9:
            raise TaxIdError("A US EIN is 9 digits. Leave it blank if you do not have one.")
        return f"{digits[:2]}-{digits[2:]}"
    if not _LOOSE.fullmatch(cleaned):
        raise TaxIdError("Enter the tax or business registration number, or leave it blank.")
    return cleaned
