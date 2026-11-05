"""Tenant catalogue matching. Names are compared in memory after a tenant-scoped read of sellable items.

Stock rows are not required. Cost columns are not read.
"""

from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product

PAGE = 8
_TOKEN = re.compile(r"[\w+-]+", re.UNICODE)
_STOP = frozenset(
    """
    do you have the a an in stock price what is this product please of for me my we can i want to know about
    show list all your store how much much? available availability pieces piece
    hello hi hey thanks thank ok yes no there again friend
    كم سعر متوفر هل لديكم اعرض
    """.split()
)
_RESTRICTED = (
    "profit",
    "margin",
    "revenue",
    "salary",
    "payroll",
    "purchase cost",
    "supplier price",
    "bank balance",
    "system prompt",
    "ignore previous",
    "ignore all",
    "all customers",
    "phone numbers",
    "full database",
    "every tenant",
    "all tenants",
    "purchase prices",
)
_FOLLOW = {
    "first": 0,
    "1st": 0,
    "second": 1,
    "2nd": 1,
    "third": 2,
    "3rd": 2,
    "fourth": 3,
    "fifth": 4,
}


def is_restricted(text: str) -> bool:
    raw = text.casefold()
    return any(phrase in raw for phrase in _RESTRICTED)


def query_tokens(text: str) -> list[str]:
    words: list[str] = []
    for word in _TOKEN.findall(text):
        folded = _stem(word.casefold())
        if folded in _STOP or len(folded) < 2:
            continue
        words.append(folded)
    return words[:8]


def follow_up_index(text: str) -> int | None:
    raw = text.casefold()
    for word, index in _FOLLOW.items():
        if word in raw:
            return index
    if any(phrase in raw for phrase in ("that one", "this one", "same product", "same one")):
        return 0
    return None


def asks_for_more(text: str) -> bool:
    raw = text.casefold()
    return "show more" in raw or "more products" in raw or "المزيد" in raw


def pieces_requested(text: str) -> int:
    match = re.search(r"\b(\d{1,4})\b", text)
    if match is None:
        return 1
    value = int(match.group(1))
    return value if 1 <= value <= 9999 else 1


def search_catalogue(db: Session, text: str, prior_ids: list[str] | None = None, offset: int = 0) -> dict:
    """Return customer-safe matches for this tenant. The session already filters other tenants."""
    if asks_for_more(text) and prior_ids:
        return _page(db, prior_ids, offset + PAGE, [])
    index = follow_up_index(text)
    if index is not None and prior_ids:
        named_first = "first" in text.casefold() or "1st" in text.casefold()
        if index == 0 and len(prior_ids) > 1 and not named_first:
            return _page(db, prior_ids, 0, [])
        if index >= len(prior_ids):
            return {"products": [], "spelling": [], "truncated": False, "all_ids": prior_ids, "offset": 0}
        return _page(db, [prior_ids[index]], 0, [])
    tokens = query_tokens(text)
    if not tokens:
        return {"products": [], "spelling": [], "truncated": False, "all_ids": [], "offset": 0}
    rows = db.execute(
        select(
            Product.id,
            Product.name,
            Product.sku,
            Product.barcode,
            Product.model_number,
            Product.category,
            Product.brand,
        )
        .where(Product.is_active.is_(True), Product.is_ingredient.is_(False))
        .order_by(Product.name)
    ).all()
    scored: list[tuple[float, str, list[str]]] = []
    for row in rows:
        score, spelling = _score(tokens, row)
        if score >= 0.78:
            scored.append((score, str(row.id), spelling))
    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return {"products": [], "spelling": [], "truncated": False, "all_ids": [], "offset": 0}
    best = scored[0][0]
    second = scored[1][0] if len(scored) > 1 else 0
    if best >= 0.84 and best - second >= 0.06:
        chosen = scored[:1]
    else:
        chosen = [item for item in scored if item[0] >= 0.78][:40]
    spelling = chosen[0][2] if len(chosen) == 1 else []
    ids = [item[1] for item in chosen]
    return _page(db, ids, 0, spelling)


def _page(db: Session, ids: list[str], offset: int, spelling: list[str]) -> dict:
    window = [_uuid(item) for item in ids[offset : offset + PAGE]]
    products = []
    if window:
        found = db.scalars(select(Product).where(Product.id.in_(window), Product.is_active.is_(True))).all()
        by_id = {str(product.id): product for product in found}
        products = [by_id[str(item)] for item in window if str(item) in by_id]
    return {
        "products": products,
        "spelling": spelling,
        "truncated": offset + PAGE < len(ids),
        "all_ids": ids,
        "offset": offset,
    }


def _uuid(value) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _stem(word: str) -> str:
    if word.endswith("s") and len(word) > 4 and not word.endswith("ss"):
        return word[:-1]
    return word


def _words(value: str | None) -> list[str]:
    found: list[str] = []
    for word in _TOKEN.findall(value or ""):
        folded = word.casefold()
        found.append(folded)
        compact = folded.replace("-", "")
        if compact != folded:
            found.append(compact)
        stemmed = _stem(folded)
        if stemmed != folded:
            found.append(stemmed)
    return found


def _score(tokens: list[str], row) -> tuple[float, list[str]]:
    sku = (row.sku or "").casefold()
    barcode = (row.barcode or "").casefold()
    if any(token == sku or token == barcode for token in tokens):
        return 1.0, []
    hay = _words(" ".join(part or "" for part in (row.name, row.sku, row.model_number, row.category, row.brand)))
    if not hay:
        return 0.0, []
    scores: list[float] = []
    spelling: list[str] = []
    for token in tokens:
        best = 0.0
        matched = token
        for word in hay:
            if token == word:
                best = 1.0
                matched = word
                break
            ratio = SequenceMatcher(None, token, word).ratio()
            if ratio > best:
                best = ratio
                matched = word
        if best < 0.78:
            return 0.0, []
        scores.append(best)
        if matched != token and best < 1:
            spelling.append(f"{token} → {matched}")
    return sum(scores) / len(scores), spelling
