"""Weighed goods. Stock and sale quantities of a sold-by-weight product count grams, while its prices and batch costs
are per kilogram, so every amount is quantity x unit / 1000. Mirrors weighed.ts in packages/shared-types."""

from typing import Protocol

GRAMS_PER_KG = 1000
# Largest single weighed line (grams); sale lines are capped at the payload's quantity limit.
MAX_LINE_GRAMS = 1_000_000


class _Weighable(Protocol):
    sold_by_weight: bool


def scale_of(product: _Weighable | None) -> int:
    """How many quantity units one price unit covers: 1000 grams per kilogram, else 1."""
    return GRAMS_PER_KG if product is not None and product.sold_by_weight else 1


def amount(quantity: int, unit_cents: int, scale: int = 1) -> int:
    """quantity x unit_cents / scale, rounded half up (exact for scale 1)."""
    if scale == 1:
        return quantity * unit_cents
    return (quantity * unit_cents + scale // 2) // scale


def format_weight(grams: int) -> str:
    return f"{grams} g" if abs(grams) < GRAMS_PER_KG else f"{grams / GRAMS_PER_KG:.3f} kg"
