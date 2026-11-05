"""Country-aware phone numbers. Valid numbers are stored as E.164. Empty stays empty.

A number that already carries a country code (`+` or the `00` access prefix) keeps that country.
A national number is parsed with the UAE rules first, because that is the phone input's default
country. It is not rewritten to another country when the UAE numbering plan accepts it. When the
UAE plan rejects it, another Gulf country is used only if exactly one of them accepts it.
"""

import re

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

DEFAULT_REGION = "AE"
GULF_REGIONS = ("AE", "SA", "QA", "KW", "BH", "OM")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _format(number: str, region: str | None) -> str | None:
    try:
        parsed = phonenumbers.parse(number, region)
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def normalize_phone(value: str | None, *, required: bool = False) -> str | None:
    """E.164 for a usable number, None when the field is blank, or ValueError when it is not a number."""
    if value is None or value.strip() == "":
        if required:
            raise ValueError("Enter a phone number.")
        return None
    compact = re.sub(r"[\s().-]", "", value.strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact.startswith("+"):
        international = _format(compact, None)
        if international is None:
            raise ValueError("Enter a valid phone number.")
        return international
    local = _format(compact, DEFAULT_REGION)
    if local is not None:
        return local
    matches: list[str] = []
    for region in GULF_REGIONS:
        if region == DEFAULT_REGION:
            continue
        found = _format(compact, region)
        if found is not None and found not in matches:
            matches.append(found)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError("Enter the phone number with its country code, for example +971501234567.")
    raise ValueError("Enter a valid phone number.")


def _calling_region(sender: str | None) -> str | None:
    digits = re.sub(r"\D", "", sender or "")
    if len(digits) < 8:
        return None
    try:
        parsed = phonenumbers.parse(f"+{digits}", None)
    except NumberParseException:
        return None
    if not phonenumbers.is_possible_number(parsed):
        return None
    return phonenumbers.region_code_for_number(parsed)


def whatsapp_destination(value: str, sender: str | None = None) -> str:
    """Digits Evolution will accept. A national number uses the connected line's country.

    `03104433311` on a Pakistan line (`923…`) becomes `923104433311`. A number that already
    carries a country code is left in that country, even when it was typed without a plus.
    """
    compact = re.sub(r"[\s().-]", "", (value or "").strip())
    if compact.startswith("00"):
        compact = f"+{compact[2:]}"
    if compact == "" or compact == "+":
        raise ValueError("Enter a WhatsApp number.")
    attempts: list[tuple[str, str | None]] = []
    if compact.startswith("+"):
        attempts.append((compact, None))
    else:
        region = _calling_region(sender)
        if region is not None:
            attempts.append((compact, region))
        attempts.append((f"+{re.sub(r'\D', '', compact)}", None))
    for number, region in attempts:
        try:
            parsed = phonenumbers.parse(number, region)
        except NumberParseException:
            continue
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164).removeprefix("+")
    raise ValueError("Enter the WhatsApp number with its country code, for example +923104433311.")


def optional_email(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().lower()
    if cleaned == "":
        return None
    if not _EMAIL.fullmatch(cleaned):
        raise ValueError("Enter a valid email address.")
    return cleaned


def search_terms(query: str) -> list[str]:
    """Digit strings that should still find a stored E.164 number."""
    digits = re.sub(r"\D", "", query)
    terms: list[str] = []
    if len(digits) >= 6:
        terms.append(digits)
        if digits.startswith("0") and len(digits) > 6:
            terms.append(digits[1:])
    try:
        canonical = normalize_phone(query)
    except ValueError:
        canonical = None
    if canonical:
        terms.append(canonical)
        terms.append(canonical.removeprefix("+"))
    unique: list[str] = []
    for term in terms:
        if term not in unique:
            unique.append(term)
    return unique
