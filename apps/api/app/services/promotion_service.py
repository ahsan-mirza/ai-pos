"""Promotions: admin CRUD, the active list registers cache, and checking what a synced sale claimed.

Registers apply promotions offline, so a sale can arrive after a promotion changed. A claim for an unknown
promotion is refused; anything else that does not match today's rules is accepted and audited."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.product import Product
from app.models.promotion import Promotion, PromotionRedemption
from app.schemas.payloads import SalePayload
from app.schemas.promotions import PromotionOut, PromotionWrite
from app.services.promotion_engine import Line, Rule, apply_promotions

PARAM_KEYS = (
    "percent_bps",
    "buy_qty",
    "get_qty",
    "get_discount_bps",
    "group_qty",
    "group_price_cents",
    "components",
    "bundle_price_cents",
)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _stats(db: Session) -> dict[uuid.UUID, tuple[int, int]]:
    rows = db.execute(
        select(
            PromotionRedemption.promotion_id,
            func.count(PromotionRedemption.id),
            func.coalesce(func.sum(PromotionRedemption.discount_cents), 0),
        ).group_by(PromotionRedemption.promotion_id)
    ).all()
    return {promotion_id: (int(count), int(total)) for promotion_id, count, total in rows}


def _out(promo: Promotion, stats: dict[uuid.UUID, tuple[int, int]]) -> PromotionOut:
    uses, given = stats.get(promo.id, (0, 0))
    params = promo.params or {}
    return PromotionOut(
        id=promo.id,
        name=promo.name,
        description=promo.description,
        kind=promo.kind,  # type: ignore[arg-type]
        product_ids=list(promo.product_ids or []),
        category_ids=list(promo.category_ids or []),
        store_ids=list(promo.store_ids or []),
        starts_at=_aware(promo.starts_at),
        ends_at=_aware(promo.ends_at),
        is_active=promo.is_active,
        coupon_code=promo.coupon_code,
        max_uses=promo.max_uses,
        uses_count=uses,
        discount_given_cents=given,
        min_spend_cents=promo.min_spend_cents,
        **{key: params.get(key) for key in PARAM_KEYS},
    )


def _apply(promo: Promotion, data: PromotionWrite) -> None:
    promo.name = data.name.strip()
    promo.description = data.description.strip()
    promo.kind = data.kind
    promo.product_ids = [str(item) for item in data.product_ids]
    promo.category_ids = [str(item) for item in data.category_ids]
    promo.store_ids = [str(item) for item in data.store_ids]
    promo.starts_at = data.starts_at
    promo.ends_at = data.ends_at
    promo.is_active = data.is_active
    promo.coupon_code = data.coupon_code
    promo.max_uses = data.max_uses
    promo.min_spend_cents = data.min_spend_cents
    params = data.model_dump(include=set(PARAM_KEYS), mode="json", exclude_none=True)
    promo.params = params


def _check_code(db: Session, data: PromotionWrite, promotion_id: uuid.UUID | None) -> None:
    if data.coupon_code is None:
        return
    taken = db.scalar(select(Promotion.id).where(Promotion.coupon_code == data.coupon_code))
    if taken is not None and taken != promotion_id:
        raise ApiError(409, "coupon_taken", f"Coupon {data.coupon_code} is already used by another promotion.")


def list_promotions(db: Session) -> list[PromotionOut]:
    stats = _stats(db)
    rows = list(db.scalars(select(Promotion).order_by(Promotion.is_active.desc(), Promotion.created_at.desc())))
    ids = {
        uuid.UUID(value)
        for row in rows
        for value in [
            *(row.product_ids or []),
            *(part["product_id"] for part in (row.params or {}).get("components") or []),
        ]
    }
    names = (
        {str(product.id): product.name for product in db.scalars(select(Product).where(Product.id.in_(ids)))}
        if ids
        else {}
    )
    out = []
    for row in rows:
        item = _out(row, stats)
        wanted = [*item.product_ids, *(part["product_id"] for part in item.components or [])]
        item.product_names = {key: names[key] for key in wanted if key in names}
        out.append(item)
    return out


def create(db: Session, data: PromotionWrite, user_id: uuid.UUID | None) -> PromotionOut:
    _check_code(db, data, None)
    promo = Promotion(created_by_id=user_id)
    _apply(promo, data)
    db.add(promo)
    db.commit()
    return _out(promo, _stats(db))


def update(db: Session, promotion_id: uuid.UUID, data: PromotionWrite) -> PromotionOut:
    promo = db.get(Promotion, promotion_id)
    if promo is None:
        raise ApiError(404, "not_found", "Promotion was not found.")
    _check_code(db, data, promo.id)
    _apply(promo, data)
    db.commit()
    return _out(promo, _stats(db))


def for_register(db: Session, store_id: uuid.UUID | None) -> list[PromotionOut]:
    """Promotions a register may need while offline: switched on, not ended, and open to its store."""
    now = datetime.now(UTC)
    stats = _stats(db)
    out = []
    for promo in db.scalars(select(Promotion).where(Promotion.is_active.is_(True))):
        if promo.ends_at is not None and _aware(promo.ends_at) <= now:  # type: ignore[operator]
            continue
        if store_id is not None and promo.store_ids and str(store_id) not in promo.store_ids:
            continue
        row = _out(promo, stats)
        if row.max_uses is not None and row.uses_count >= row.max_uses:
            continue
        out.append(row)
    return out


def rule_of(promo: Promotion) -> Rule:
    return Rule.from_dict(
        {
            "id": str(promo.id),
            "kind": promo.kind,
            "product_ids": promo.product_ids,
            "category_ids": promo.category_ids,
            "min_spend_cents": promo.min_spend_cents,
            **(promo.params or {}),
        }
    )


def _live(promo: Promotion, at: datetime, store_id: uuid.UUID, coupon: str | None, uses: int) -> list[str]:
    """Why a promotion did not apply to this sale (empty when it did)."""
    problems = []
    if not promo.is_active:
        problems.append("switched off")
    if promo.starts_at is not None and _aware(promo.starts_at) > at:  # type: ignore[operator]
        problems.append("not started")
    if promo.ends_at is not None and _aware(promo.ends_at) <= at:  # type: ignore[operator]
        problems.append("ended")
    if promo.store_ids and str(store_id) not in promo.store_ids:
        problems.append("not offered at this branch")
    if promo.coupon_code is not None and promo.coupon_code != coupon:
        problems.append("coupon not entered")
    if promo.max_uses is not None and uses >= promo.max_uses:
        problems.append("use limit reached")
    return problems


def require_known(db: Session, data: SalePayload) -> None:
    """Runs before anything is written: a claim for a promotion that does not exist refuses the sale."""
    wanted = {item.promotion_id for item in data.items if item.promotion_id is not None}
    if wanted and len(db.scalars(select(Promotion.id).where(Promotion.id.in_(wanted))).all()) != len(wanted):
        raise SyncRejected("The sale claims a promotion this business does not have.")


def verify_and_redeem(db: Session, data: SalePayload, *, sold_at: datetime) -> list[str]:
    claimed: dict[uuid.UUID, int] = defaultdict(int)
    for item in data.items:
        if item.promotion_id is not None:
            claimed[item.promotion_id] += item.discount_cents
    if not claimed:
        return []
    coupon = data.coupon_code.strip().upper() if data.coupon_code else None
    promotions = {promo_id: db.get(Promotion, promo_id) for promo_id in claimed}
    missing = [str(promo_id) for promo_id, promo in promotions.items() if promo is None]
    if missing:
        raise SyncRejected("The sale claims a promotion this business does not have.")
    stats = _stats(db)
    issues: list[str] = []
    if data.sale_type != "RETAIL":
        issues.append("Promotions are for retail sales; this was a wholesale sale.")

    live_rules = []
    for promo in db.scalars(select(Promotion)):
        if not _live(promo, sold_at, data.store_id, coupon, stats.get(promo.id, (0, 0))[0]):
            live_rules.append(rule_of(promo))
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in data.items})))
    }
    lines = [
        Line(
            line_id=str(item.id),
            product_id=str(item.product_id),
            category_id=str(products[item.product_id].category_id)
            if item.product_id in products and products[item.product_id].category_id
            else None,
            unit_price_cents=item.unit_price_cents,
            quantity=item.quantity,
        )
        for item in data.items
        # Weighed goods (grams at a per-kg price) never take promotions.
        if not (item.product_id in products and products[item.product_id].sold_by_weight)
    ]
    allowed: dict[str, int] = defaultdict(int)
    for award in apply_promotions(lines, live_rules):
        allowed[award.promotion_id] += award.discount_cents

    for promo_id, discount in claimed.items():
        promo = promotions[promo_id]
        assert promo is not None
        problems = _live(promo, sold_at, data.store_id, coupon, stats.get(promo.id, (0, 0))[0])
        if problems:
            issues.append(f"{promo.name}: {', '.join(problems)}.")
        elif discount > (limit := allowed.get(str(promo_id), 0)):
            issues.append(f"{promo.name}: claimed {discount / 100:.2f} but the rules allow {limit / 100:.2f}.")
        db.add(
            PromotionRedemption(
                promotion_id=promo_id,
                sale_id=data.id,
                store_id=data.store_id,
                discount_cents=discount,
                coupon_code=coupon if promo.coupon_code else None,
            )
        )
    return issues
