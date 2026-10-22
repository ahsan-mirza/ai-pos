import re

from sqlalchemy import ColumnElement, or_

from app.models.product import Product
from app.services.identifiers import identifier_hash, is_valid_imei

MAX_TOKENS = 6
_IDENTIFIER = re.compile(r"[A-Za-z0-9-]{4,64}")


def tokens(query: str) -> list[str]:
    return [token for token in query.strip().lower().split() if token][:MAX_TOKENS]


def _like(token: str) -> str:
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _compact(value: str) -> str:
    return re.sub(r"[\s\-_./]", "", value)


def token_condition(token: str) -> ColumnElement[bool]:
    """One search word matching name, model, barcode, SKU, category, or brand (partial, case-insensitive); model,
    SKU and barcode also match with separators removed. Both are LIKEs on Product.search_text, which is lowercased."""
    word = token.lower()
    conditions: list[ColumnElement[bool]] = [Product.search_text.like(_like(word), escape="\\")]
    compact = _compact(word)
    if compact and compact != word:
        conditions.append(Product.search_text.like(_like(compact), escape="\\"))
    return or_(*conditions)


def identifier_candidates(query: str) -> dict[str, str]:
    """Hashes an IMEI/serial-shaped query the same way stored identifiers are hashed. Exact match only:
    the values are encrypted at rest, so partial matching is impossible by design."""
    value = query.strip()
    if _IDENTIFIER.fullmatch(value) is None:
        return {}
    candidates = {identifier_hash(value.upper()): "serial"}
    if is_valid_imei(value):
        candidates[identifier_hash(value)] = "imei"
    return candidates
