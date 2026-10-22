"""Barcode numbers and symbols: EAN-13 check digits, in-store EAN-13 numbering, and the bar patterns labels print
(EAN-13 for 13-digit codes, Code 128 for anything else)."""

import secrets

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.product import Product

# --- Numbers --------------------------------------------------------------------------------------------------


def ean13(body: str) -> str:
    """Appends the check digit to a 12-digit body."""
    if len(body) != 12 or not body.isdigit():
        raise ValueError("An EAN-13 body is 12 digits.")
    total = sum(int(digit) * (3 if position % 2 else 1) for position, digit in enumerate(body))
    return body + str((10 - total % 10) % 10)


def is_ean13(code: str) -> bool:
    return len(code) == 13 and code.isdigit() and ean13(code[:12]) == code


def code_taken(db: Session, code: str, reserved: set[str]) -> bool:
    lowered = code.lower()
    if lowered in reserved:
        return True
    clash = db.scalar(
        select(Product.id).where(or_(func.lower(Product.sku) == lowered, func.lower(Product.barcode) == lowered))
    )
    return clash is not None


def in_store_ean13(db: Session, reserved: set[str]) -> str:
    """A free in-store EAN-13 (prefixes 200-299 are reserved by GS1 for restricted, in-store numbering)."""
    for _ in range(20):
        candidate = ean13("200" + "".join(secrets.choice("0123456789") for _ in range(9)))
        if not code_taken(db, candidate, reserved):
            reserved.add(candidate)
            return candidate
    raise ApiError(409, "conflict", "Could not generate a unique barcode. Try again.")


# --- Symbols ---------------------------------------------------------------------------------------------------

_EAN_L = ("0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011")
_EAN_G = tuple("".join("1" if bit == "0" else "0" for bit in reversed(code)) for code in _EAN_L)
_EAN_R = tuple("".join("1" if bit == "0" else "0" for bit in code) for code in _EAN_L)
_EAN_PARITY = ("LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL")


def ean13_modules(code: str) -> str:
    """The 95 modules of an EAN-13 symbol as '1' (bar) and '0' (space)."""
    if not is_ean13(code):
        raise ValueError(f"{code} is not a valid EAN-13.")
    parity = _EAN_PARITY[int(code[0])]
    left = "".join(
        (_EAN_L if side == "L" else _EAN_G)[int(digit)] for side, digit in zip(parity, code[1:7], strict=True)
    )
    right = "".join(_EAN_R[int(digit)] for digit in code[7:])
    return "101" + left + "01010" + right + "101"


# Code 128 patterns: bar/space widths for values 0-106 (106 is STOP, with its final 2-module bar).
_C128 = (
    "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 "
    "113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 "
    "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 "
    "113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 "
    "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 "
    "241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 "
    "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 "
    "211232 2331112"
).split()
_START_B, _STOP = 104, 106


def code128_modules(text: str) -> str:
    """Code 128 set B (printable ASCII) as '1'/'0' modules, with quiet zones left to the caller."""
    if not text or any(not 32 <= ord(char) <= 126 for char in text):
        raise ValueError("Code 128 labels take printable ASCII only.")
    values = [_START_B, *(ord(char) - 32 for char in text)]
    checksum = (values[0] + sum(position * value for position, value in enumerate(values[1:], start=1))) % 103
    modules = []
    for value in [*values, checksum, _STOP]:
        for index, width in enumerate(_C128[value]):
            modules.append(("1" if index % 2 == 0 else "0") * int(width))
    return "".join(modules)
