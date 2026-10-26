"""Promotion engine. Mirrors packages/shared-types/src/promotions.ts; both are checked against
packages/shared-types/fixtures/promotion-cases.json so a register and the API agree on every discount.

Every unit of an eligible line is ranked by price (dearest first, then cart order). The promotion that saves
the most is applied first and claims the lines it used; the next best works on what is left. A line is
discounted by at most one promotion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    product_ids: tuple[str, ...] = ()
    category_ids: tuple[str, ...] = ()
    percent_bps: int = 0
    buy_qty: int = 0
    get_qty: int = 0
    get_discount_bps: int = 10_000
    group_qty: int = 0
    group_price_cents: int = 0
    components: tuple[tuple[str, int], ...] = ()
    bundle_price_cents: int = 0
    min_spend_cents: int = 0
    amount_cents: int = 0
    max_discount_cents: int = 0

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Rule:
        return cls(
            id=str(raw["id"]),
            kind=raw["kind"],
            product_ids=tuple(str(item) for item in raw.get("product_ids") or ()),
            category_ids=tuple(str(item) for item in raw.get("category_ids") or ()),
            percent_bps=int(raw.get("percent_bps") or 0),
            buy_qty=int(raw.get("buy_qty") or 0),
            get_qty=int(raw.get("get_qty") or 0),
            get_discount_bps=int(raw["get_discount_bps"]) if raw.get("get_discount_bps") is not None else 10_000,
            group_qty=int(raw.get("group_qty") or 0),
            group_price_cents=int(raw.get("group_price_cents") or 0),
            components=tuple((str(part["product_id"]), int(part["quantity"])) for part in raw.get("components") or ()),
            bundle_price_cents=int(raw.get("bundle_price_cents") or 0),
            min_spend_cents=int(raw.get("min_spend_cents") or 0),
            amount_cents=int(raw.get("amount_cents") or 0),
            max_discount_cents=int(raw.get("max_discount_cents") or 0),
        )


@dataclass(frozen=True)
class Line:
    line_id: str
    product_id: str
    category_id: str | None
    unit_price_cents: int
    quantity: int


@dataclass(frozen=True)
class Award:
    line_id: str
    promotion_id: str
    discount_cents: int


@dataclass
class _Evaluation:
    saving: int = 0
    discounts: dict[str, int] = field(default_factory=dict)
    used: list[str] = field(default_factory=list)

    def use(self, line_id: str) -> None:
        if line_id not in self.used:
            self.used.append(line_id)

    def add(self, line_id: str, amount: int) -> None:
        self.discounts[line_id] = self.discounts.get(line_id, 0) + amount


def _percent(amount: int, bps: int) -> int:
    return (amount * bps + 5000) // 10_000


def _eligible(rule: Rule, line: Line) -> bool:
    if rule.kind == "BUNDLE":
        return any(product_id == line.product_id for product_id, _ in rule.components)
    if not rule.product_ids and not rule.category_ids:
        return True
    return line.product_id in rule.product_ids or (
        line.category_id is not None and line.category_id in rule.category_ids
    )


def _units(entries: list[tuple[int, Line]]) -> list[tuple[str, int, int]]:
    units = [(line.line_id, line.unit_price_cents, order) for order, line in entries for _ in range(line.quantity)]
    return sorted(units, key=lambda unit: (-unit[1], unit[2]))


def _cap(result: _Evaluation, limit: int) -> None:
    total = sum(result.discounts.values())
    if limit <= 0 or total <= limit:
        return
    items = list(result.discounts.items())
    running = 0
    scaled: dict[str, int] = {}
    for index, (line_id, amount) in enumerate(items):
        take = max(0, limit - running) if index == len(items) - 1 else amount * limit // total
        scaled[line_id] = take
        running += take
    result.discounts = {line_id: amount for line_id, amount in scaled.items() if amount > 0}


def _spread(group: list[tuple[str, int, int]], discount: int, result: _Evaluation) -> None:
    remaining = discount
    for line_id, price, _ in group:
        if remaining <= 0:
            break
        take = min(price, remaining)
        result.add(line_id, take)
        remaining -= take


def _evaluate(rule: Rule, entries: list[tuple[int, Line]]) -> _Evaluation:
    result = _Evaluation()
    pool = [(order, line) for order, line in entries if _eligible(rule, line)]
    if rule.kind == "PERCENT_OFF":
        for _, line in pool:
            discount = _percent(line.unit_price_cents * line.quantity, rule.percent_bps)
            if discount > 0:
                result.add(line.line_id, discount)
                result.use(line.line_id)
        if rule.max_discount_cents:
            _cap(result, rule.max_discount_cents)
    elif rule.kind == "AMOUNT_OFF" and rule.amount_cents > 0:
        units = _units(pool)
        gross = sum(price for _, price, _ in units)
        discount = min(rule.amount_cents, gross)
        if discount > 0:
            for line_id, _, _ in units:
                result.use(line_id)
            _spread(units, discount, result)
    elif rule.kind == "BUY_X_GET_Y" and rule.buy_qty > 0 and rule.get_qty > 0:
        size = rule.buy_qty + rule.get_qty
        units = _units(pool)
        for start in range(0, len(units) - size + 1, size):
            group = units[start : start + size]
            for line_id, _, _ in group:
                result.use(line_id)
            for line_id, price, _ in group[rule.buy_qty :]:
                result.add(line_id, _percent(price, rule.get_discount_bps))
    elif rule.kind == "MIX_MATCH" and rule.group_qty > 0:
        units = _units(pool)
        for start in range(0, len(units) - rule.group_qty + 1, rule.group_qty):
            group = units[start : start + rule.group_qty]
            discount = sum(price for _, price, _ in group) - rule.group_price_cents
            if discount <= 0:
                continue
            for line_id, _, _ in group:
                result.use(line_id)
            _spread(group, discount, result)
    elif rule.kind == "BUNDLE":
        parts = [(product_id, quantity) for product_id, quantity in rule.components if quantity > 0]
        by_product = {
            product_id: _units([(order, line) for order, line in pool if line.product_id == product_id])
            for product_id, _ in parts
        }
        bundles = min((len(by_product[product_id]) // quantity for product_id, quantity in parts), default=0)
        for bundle in range(bundles):
            group = [
                unit
                for product_id, quantity in parts
                for unit in by_product[product_id][bundle * quantity : (bundle + 1) * quantity]
            ]
            discount = sum(price for _, price, _ in group) - rule.bundle_price_cents
            if discount <= 0:
                break
            group.sort(key=lambda unit: (-unit[1], unit[2]))
            for line_id, _, _ in group:
                result.use(line_id)
            _spread(group, discount, result)
    result.saving = sum(result.discounts.values())
    return result


def apply_promotions(lines: list[Line], rules: list[Rule]) -> list[Award]:
    """Discounts for a cart. Pass only rules already active for the store, time and coupon."""
    cart_gross = sum(line.unit_price_cents * line.quantity for line in lines)
    remaining = [(order, line) for order, line in enumerate(lines) if line.quantity > 0]
    candidates = sorted((rule for rule in rules if cart_gross >= rule.min_spend_cents), key=lambda rule: rule.id)
    awards: list[Award] = []
    while True:
        best: tuple[Rule, _Evaluation] | None = None
        for rule in candidates:
            result = _evaluate(rule, remaining)
            if result.saving > 0 and (best is None or result.saving > best[1].saving):
                best = (rule, result)
        if best is None:
            break
        rule, result = best
        for line_id in result.used:
            discount = result.discounts.get(line_id, 0)
            if discount > 0:
                awards.append(Award(line_id=line_id, promotion_id=rule.id, discount_cents=discount))
        used = set(result.used)
        remaining = [(order, line) for order, line in remaining if line.line_id not in used]
        candidates = [item for item in candidates if item.id != rule.id]
    position = {line.line_id: index for index, line in enumerate(lines)}
    return sorted(awards, key=lambda award: position.get(award.line_id, 0))
