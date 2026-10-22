"""Cashier discounts: a reason from the business's till rules, and a limit per role. Within their own limit a cashier
holding pos:discount discounts alone; above it (or without the permission) a manager whose limit covers it approves."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import SyncRejected
from app.core.permissions import Permission
from app.models.product import Product
from app.models.user import User
from app.schemas.payloads import SaleItemPayload
from app.schemas.pos_policy import PosPolicy
from app.services.settings_service import pos_policy


def limit_bps(user: User | None, policy: PosPolicy) -> int:
    """Largest discount the user gives alone, in basis points of the line; 0 without pos:discount."""
    if user is None or Permission.POS_DISCOUNT.value not in user.permissions:
        return 0
    role_limit = user.role.max_discount_bps if user.role is not None else None
    return policy.discounts.default_limit_bps if role_limit is None else role_limit


def share_bps(discount_cents: int, before_cents: int) -> int:
    """Discount as basis points of the line before it, rounded up so 10.01% is not taken for 10%."""
    if before_cents <= 0:
        return 10_000
    return -(-discount_cents * 10_000 // before_cents)


def check_line(
    db: Session,
    item: SaleItemPayload,
    *,
    product: Product,
    before_cents: int,
    cashier: User | None,
    store_id: uuid.UUID,
) -> User | None:
    """Validates a cashier discount and returns the approving manager, if one was needed."""
    policy = pos_policy(db)
    if item.discount_reason not in {reason.key for reason in policy.discounts.reasons}:
        raise SyncRejected(f"Discount reason {item.discount_reason!r} is not one of the business's reasons.")
    if product.sold_by_weight:
        raise SyncRejected("Discounts do not apply to weighed items.")
    share = share_bps(item.manual_discount_cents, before_cents)
    if share <= limit_bps(cashier, policy):
        return None
    if item.discount_override is None:
        raise SyncRejected(
            f"A {share / 100:.2f}% discount on {product.name} is above the cashier's limit and needs a manager."
        )
    approver = db.get(User, item.discount_override.approved_by_id)
    if approver is None:
        raise SyncRejected("The manager approving the discount does not exist.")
    if approver.store_id is not None and approver.store_id != store_id:
        raise SyncRejected("The approving manager is not assigned to this store.")
    if share > limit_bps(approver, policy):
        raise SyncRejected(f"{approver.full_name} cannot approve a {share / 100:.2f}% discount.")
    return approver
