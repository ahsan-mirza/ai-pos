import hashlib
import re

from app.core.errors import SyncRejected


def is_valid_imei(value: str) -> bool:
    if re.fullmatch(r"\d{15}", value) is None:
        return False
    total = 0
    for index, char in enumerate(reversed(value)):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def normalize_identifier(kind: str, value: str) -> str:
    cleaned = value.strip()
    if kind == "imei":
        if not is_valid_imei(cleaned):
            raise SyncRejected("IMEI failed Luhn validation.")
        return cleaned
    if kind != "serial":
        raise SyncRejected("Identifier kind is invalid.")
    if re.fullmatch(r"[A-Za-z0-9-]{4,64}", cleaned) is None:
        raise SyncRejected("Serial number format is invalid.")
    return cleaned.upper()


def identifier_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


SUFFIX_LENGTH = 6


def identifier_suffix(normalized: str) -> str:
    """The last characters kept in plain text for "ends with" search; the full value stays encrypted."""
    return normalized.upper()[-SUFFIX_LENGTH:]
