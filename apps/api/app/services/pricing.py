"""Tier, volume and price-list pricing. Mirrors packages/shared-types/src/pricing.ts exactly; both are checked
against packages/shared-types/fixtures/pricing-cases.json and price-list-cases.json."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

# Lower tiers first. A tier without its own row falls back to the nearest lower tier that has one.
TIER_ORDER = ("RETAIL", "TIER_1", "TIER_2", "DISTRIBUTOR")
DEFAULT_WHOLESALE_TIER = "TIER_1"
# Precedence when two sources give the same price: the customer's own list first, the tier price last.
SCOPE_RANK = {"customer": 0, "group": 1, "store": 2, "global": 3}

PriceSource = Literal["retail", "tier", "volume", "customer_list", "group_list", "store_list", "global_list"]


@dataclass(frozen=True)
class PriceResolution:
    price_cents: int
    tier: str
    source: PriceSource
    min_order_quantity: int
    # The customer's own tier row exists but its minimum order quantity was not met.
    moq_shortfall: int


def effective_tier(sale_type: str, customer_tier: str | None) -> str:
    if sale_type != "WHOLESALE":
        return "RETAIL"
    if customer_tier is None:
        return DEFAULT_WHOLESALE_TIER
    return customer_tier


def _field(row: Any, name: str) -> Any:
    return row[name] if isinstance(row, Mapping) else getattr(row, name)


def resolve_price(retail_cents: int, prices: Iterable[Any], tier: str, pieces: int) -> PriceResolution:
    """Unit price per piece for `pieces` at `tier`. `prices` are product_prices rows (objects or dicts)."""
    rows = {str(_field(row, "price_tier")): row for row in prices}
    wanted = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
    shortfall = 0
    for index in range(wanted, -1, -1):
        name = TIER_ORDER[index]
        row = rows.get(name)
        if row is None and name != "RETAIL":
            continue
        moq = int(_field(row, "min_order_quantity")) if row is not None else 1
        if name != "RETAIL" and pieces < moq:
            if index == wanted:
                shortfall = moq - pieces
            continue
        base = retail_cents if name == "RETAIL" else int(_field(row, "price_cents"))
        best = base
        breaks = list(_field(row, "volume_discounts") or []) if row is not None else []
        for item in breaks:
            min_qty = int(_field(item, "min_qty"))
            price = int(_field(item, "price_cents"))
            if pieces >= min_qty and price < best:
                best = price
        source: PriceSource = "volume" if best < base else ("retail" if name == "RETAIL" else "tier")
        return PriceResolution(
            price_cents=best,
            tier=name,
            source=source,
            min_order_quantity=moq,
            moq_shortfall=shortfall,
        )
    return PriceResolution(
        price_cents=retail_cents, tier="RETAIL", source="retail", min_order_quantity=1, moq_shortfall=0
    )


@dataclass(frozen=True)
class ListResolution:
    price_cents: int
    source: PriceSource
    tier: str
    price_list_id: str | None
    # Every price a valid source offered (tier result included): a register on an older list is not wrong.
    candidates: tuple[int, ...]


def _instant(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def entry_applies(entry: Any, *, customer_id: Any, group_id: Any, store_id: Any, at: Any) -> bool:
    """Whether a price-list entry (one list's item for one product) is in scope and in date at `at`."""
    if not _field(entry, "is_active"):
        return False
    scope = str(_field(entry, "scope"))
    owner = _field(entry, "scope_id")
    wanted = {"customer": customer_id, "group": group_id, "store": store_id}.get(scope)
    if scope != "global" and (owner is None or wanted is None or str(owner) != str(wanted)):
        return False
    moment = _instant(at)
    start, end = _instant(_field(entry, "valid_from")), _instant(_field(entry, "valid_to"))
    if moment is not None and start is not None and moment < start:
        return False
    return not (moment is not None and end is not None and moment >= end)


def _discounted(cents: int, bps: int) -> int:
    return (cents * (10_000 - bps) + 5_000) // 10_000


def resolve_with_lists(
    retail_cents: int,
    prices: Iterable[Any],
    tier: str,
    pieces: int,
    entries: Iterable[Any],
    *,
    customer_id: Any = None,
    group_id: Any = None,
    store_id: Any = None,
    at: Any = None,
) -> ListResolution:
    """The lowest valid price for `pieces`: price lists (customer, group, store, business-wide) against the tier
    and volume price. A discount entry takes its basis points off the tier price; equal prices go to the more
    specific scope, then the higher priority."""
    base = resolve_price(retail_cents, prices, tier, pieces)
    best = (base.price_cents, 4, 0)
    chosen: tuple[PriceSource, str | None] = (base.source, None)
    candidates = {base.price_cents}
    for entry in entries:
        if not entry_applies(entry, customer_id=customer_id, group_id=group_id, store_id=store_id, at=at):
            continue
        if pieces < int(_field(entry, "min_qty") or 1):
            continue
        fixed = _field(entry, "price_cents")
        price = int(fixed) if fixed is not None else _discounted(base.price_cents, int(_field(entry, "discount_bps")))
        for item in _field(entry, "volume_breaks") or []:
            if pieces >= int(_field(item, "min_qty")) and int(_field(item, "price_cents")) < price:
                price = int(_field(item, "price_cents"))
        scope = str(_field(entry, "scope"))
        rank = (price, SCOPE_RANK[scope], -int(_field(entry, "priority") or 0))
        candidates.add(price)
        if rank < best:
            best = rank
            list_id = _field(entry, "price_list_id")
            chosen = (f"{scope}_list", str(list_id) if list_id is not None else None)  # type: ignore[assignment]
    return ListResolution(
        price_cents=best[0],
        source=chosen[0],
        tier=base.tier,
        price_list_id=chosen[1],
        candidates=tuple(sorted(candidates)),
    )
