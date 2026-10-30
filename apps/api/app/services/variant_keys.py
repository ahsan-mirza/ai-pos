"""Canonical variant identity and price resolution.

A variant is a product. Its signature is the sorted attribute combination, so the same size and colour
cannot be inserted twice for one model. Prices resolve as an explicit override, then the highest matching
attribute rule, then the model's default.
"""

from __future__ import annotations

from typing import Any


def variant_signature(attributes: dict[str, str] | None) -> str:
    pairs: list[tuple[str, str]] = []
    for key, raw in (attributes or {}).items():
        name = str(key).strip().lower().replace(" ", "_")
        text = " ".join(str(raw).split())
        if name and text:
            pairs.append((name, text.lower()))
    pairs.sort()
    return "|".join(f"{key}={value}" for key, value in pairs)


def apply_signature(product: Any) -> None:
    """Sets the stored signature. Products that are not variants stay null so they are not part of the unique key."""
    if product.product_model_id is None:
        product.variant_signature = None
        return
    product.variant_signature = variant_signature(product.variant_attributes) or None


def variant_swatches(model: Any, attributes: dict[str, str] | None) -> dict[str, str]:
    """Hex colour for each of this variant's values, taken from the model's swatch map."""
    if model is None:
        return {}
    book = model.axis_swatches or {}
    found: dict[str, str] = {}
    for key, value in (attributes or {}).items():
        colour = (book.get(key) or {}).get(value)
        if isinstance(colour, str) and colour:
            found[key] = colour
    return found


def rules_from_values(axes: list[tuple[str, list[str]]], price_by_value: dict[str, int]) -> list[dict[str, Any]]:
    """Attaches each value price to the axis it belongs to. A value on no axis matches any attribute."""
    rules: list[dict[str, Any]] = []
    for raw_value, price in price_by_value.items():
        value = " ".join(str(raw_value).split())
        key = ""
        for axis_key, values in axes:
            if any(item.lower() == value.lower() for item in values):
                key = axis_key
                break
        rules.append({"key": key, "value": value, "price_cents": int(price)})
    return rules


def resolved_price(default_cents: int, rules: list[Any], attributes: dict[str, str] | None) -> tuple[int, str]:
    """Highest matching attribute rule, otherwise the model default. Overrides are applied by the caller."""
    attrs = attributes or {}
    matched: list[int] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        key = str(rule.get("key") or "")
        value = str(rule.get("value") or "")
        price = rule.get("price_cents")
        if not isinstance(price, int) or not value:
            continue
        if key:
            if str(attrs.get(key, "")).lower() == value.lower():
                matched.append(price)
        elif any(str(item).lower() == value.lower() for item in attrs.values()):
            matched.append(price)
    if matched:
        return max(matched), "rule"
    return default_cents, "default"
