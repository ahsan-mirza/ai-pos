"""Campaign text grounded in this store's records. A model may not add prices or discounts that are not stored."""

from __future__ import annotations

import re
import uuid

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ApiError
from app.models.product import Product
from app.models.promotion import Promotion
from app.services.settings_service import load_settings

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?%?")


def generate(db: Session, settings: Settings, data: dict) -> dict:
    product = _product(db, data.get("product_id"))
    promotion = _promotion(db, data.get("promotion_id"))
    facts, missing = _facts(product, promotion, bool(data.get("include_price")))
    business = load_settings(db).legal_name or "our store"
    draft = _builtin(data.get("objective") or "announcement", business, product, promotion, facts)
    written = draft
    if settings.assistant_provider == "ollama":
        written = _ollama(settings, draft, facts) or draft
        if not _only_known_numbers(written, " ".join(facts)):
            written = draft
    return {
        "title": _title(data.get("objective") or "announcement", product, promotion),
        "body": written,
        "facts": facts,
        "missing": missing,
        "origin": "ai",
    }


def _product(db: Session, raw: object) -> Product | None:
    if not raw:
        return None
    row = db.get(Product, uuid.UUID(str(raw)))
    if row is None:
        raise ApiError(404, "not_found", "Product not found.")
    return row


def _promotion(db: Session, raw: object) -> Promotion | None:
    if not raw:
        return None
    row = db.get(Promotion, uuid.UUID(str(raw)))
    if row is None:
        raise ApiError(404, "not_found", "Promotion not found.")
    return row


def _facts(product: Product | None, promotion: Promotion | None, include_price: bool) -> tuple[list[str], list[str]]:
    facts: list[str] = []
    missing: list[str] = []
    if product is not None:
        facts.append(f"Product: {product.name}")
        if product.category:
            facts.append(f"Category: {product.category}")
        if include_price:
            facts.append(f"Catalog price cents: {product.price_cents}")
        else:
            missing.append("price")
    elif include_price:
        missing.append("price")
    if promotion is not None:
        facts.append(f"Promotion: {promotion.name}")
        if promotion.description:
            facts.append(f"Details: {promotion.description}")
        if promotion.starts_at is not None:
            facts.append(f"Starts: {promotion.starts_at.date().isoformat()}")
        if promotion.ends_at is not None:
            facts.append(f"Ends: {promotion.ends_at.date().isoformat()}")
        else:
            missing.append("promotion end date")
    return facts, missing


def _title(objective: str, product: Product | None, promotion: Promotion | None) -> str:
    if product is not None and objective == "new_product":
        return f"New arrival: {product.name}"[:120]
    if promotion is not None:
        return f"Offer: {promotion.name}"[:120]
    labels = {
        "new_product": "New arrivals",
        "promotion": "A current offer",
        "seasonal": "Seasonal update",
        "reengagement": "We miss you",
        "appreciation": "Thank you",
        "recommendation": "Something you may like",
        "announcement": "An update from us",
    }
    return labels.get(objective, "An update from us")


def _builtin(
    objective: str,
    business: str,
    product: Product | None,
    promotion: Promotion | None,
    facts: list[str],
) -> str:
    name = product.name if product is not None else "new products"
    if objective == "reengagement":
        return f"It's been a while since your last visit to {business}. We would like to welcome you back."
    if objective == "appreciation":
        return f"Thank you for being a customer of {business}."
    if promotion is not None:
        detail = promotion.description or "Ask us what is included."
        window = ""
        if promotion.ends_at is not None:
            window = f" It runs until {promotion.ends_at.date().isoformat()}."
        return f"{business} has an offer: {promotion.name}. {detail}{window}"
    if product is not None:
        price = ""
        if any(fact.startswith("Catalog price cents:") for fact in facts):
            price = f" The catalogue price is {product.price_cents} cents."
        return f"Good news from {business}. {name} is now in the catalogue.{price}"
    return f"{business} has an update for customers who asked to hear from us."


def _only_known_numbers(text: str, allowed: str) -> bool:
    return all(number in allowed for number in _NUMBER.findall(text))


def _ollama(settings: Settings, draft: str, facts: list[str]) -> str:
    try:
        import httpx
    except ImportError:
        return ""
    prompt = (
        "Rewrite this WhatsApp marketing draft in the same facts. "
        "Do not add prices, discounts, stock, or dates that are not in the facts. "
        f"Facts: {'; '.join(facts) or 'none'}. Draft: {draft}"
    )
    try:
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={"model": settings.ollama_model, "prompt": prompt, "stream": False},
            timeout=settings.ollama_chat_timeout_seconds,
        )
        response.raise_for_status()
        text = str(response.json().get("response") or "").strip()
    except Exception:
        return ""
    return text[:1000]
