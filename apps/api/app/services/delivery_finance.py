"""Delivery payment arrangements.

Kitchen progress, the rider's trip, and money are separate. A sale is still the only
financial document: customer credit posts to the existing ledger, and COD cash enters
the drawer only as a pay-in when a cashier confirms the handover.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.restaurant import CodHandover, OpenOrder, OpenOrderItem
from app.models.sale import Sale
from app.models.shift import CashMovement, RegisterShift
from app.models.user import User
from app.services import audit, ledger_service

ARRANGEMENTS = ("PAID_NOW", "CREDIT", "COD")
DELIVERY_STATES = ("PENDING", "ASSIGNED", "OUT_FOR_DELIVERY", "DELIVERED", "FAILED", "RETURNED", "CANCELLED")
COD_SALE_STATUSES = ("COD_AWAITING", "COD_PARTIAL")


def payment_state(order: OpenOrder, sale: Sale | None) -> str | None:
    """What the order still owes. Delivery progress does not decide this."""
    if order.service_type != "DELIVERY":
        return None
    if order.delivery_status == "CANCELLED" and order.cod_handed_cents == 0:
        return "CANCELLED"
    if order.payment_arrangement == "COD" or (sale is not None and sale.payment_status in COD_SALE_STATUSES):
        expected = order.cod_expected_cents or (sale.total_cents if sale is not None else 0)
        handed = order.cod_handed_cents
        if expected > 0 and handed >= expected:
            return "PAID"
        if handed > 0:
            return "COD_PARTIAL"
        if order.delivery_status == "DELIVERED" or order.cod_collected_cents > 0:
            return "COD_AWAITING_HANDOVER"
        return "COD_AWAITING_COLLECTION"
    if sale is None:
        return "UNPAID"
    if sale.due_balance_cents <= 0 or sale.payment_status == "PAID":
        return "PAID"
    if order.payment_arrangement == "CREDIT" or sale.payment_status == "ON_ACCOUNT_UNPAID":
        return "PARTIAL" if sale.amount_paid_cents else "CREDIT_OUTSTANDING"
    return "PARTIAL" if sale.amount_paid_cents else "UNPAID"


def remember_sale(order: OpenOrder, sale: Sale, methods: set[str]) -> bool:
    """Record how a delivery sale is meant to be paid.

    Returns True when the tab must stay open because the store has not been paid.
    """
    if order.service_type != "DELIVERY":
        return False
    if order.delivery_status is None:
        order.delivery_status = "PENDING"
    if "cod" in methods:
        order.payment_arrangement = "COD"
        order.cod_expected_cents = sale.total_cents
        return sale.due_balance_cents > 0
    if sale.due_balance_cents > 0:
        order.payment_arrangement = "CREDIT"
        return True
    order.payment_arrangement = order.payment_arrangement or "PAID_NOW"
    return False


def finish_delivery(order: OpenOrder) -> None:
    """Close the tab only when the food has been delivered and the sale is fully settled."""
    if order.service_type != "DELIVERY" or order.status != "OPEN":
        return
    live = [item for item in order.items if item.voided_at is None]
    if not live or any(item.paid_sale_id is None for item in live):
        return
    if order.delivery_status != "DELIVERED":
        return
    order.status = "SETTLED"
    order.closed_at = datetime.now(UTC)
    # Channel money can post earlier. The channel ticket completes only once the meal has arrived.
    if order.channel_id is not None and order.channel_status not in {"REJECTED", "COMPLETED"}:
        order.channel_status = "COMPLETED"


def mark_lines_paid(order: OpenOrder, sale_id: uuid.UUID) -> None:
    for item in order.items:
        if item.voided_at is None and item.paid_sale_id is None:
            item.paid_sale_id = sale_id


def note_sale_paid(db: Session, sale: Sale) -> None:
    """A later customer payment cleared a delivery sale. The trip status is left as it is."""
    if sale.order_id is None or sale.due_balance_cents > 0 or sale.payment_status in COD_SALE_STATUSES:
        return
    order = db.get(OpenOrder, sale.order_id)
    if order is None or order.service_type != "DELIVERY" or order.status != "OPEN":
        return
    mark_lines_paid(order, sale.id)
    finish_delivery(order)
    order.revision += 1
    order.updated_at = datetime.now(UTC)


def latest_sale(db: Session, order_id: uuid.UUID) -> Sale | None:
    statement = (
        select(Sale)
        .where(Sale.order_id == order_id, Sale.status == "completed")
        .order_by(Sale.created_at.desc())
    )
    return db.scalars(statement).first()


def guard_void(order: OpenOrder) -> None:
    if order.service_type != "DELIVERY":
        return
    if order.cod_handed_cents > 0 or order.cod_collected_cents > 0:
        raise ApiError(
            409,
            "cod_outstanding",
            "Rider cash is still outstanding. Reconcile the handover before cancelling this delivery.",
        )


def release_on_void(db: Session, order: OpenOrder, user_id: uuid.UUID) -> None:
    """A cancelled delivery with nothing collected drops the customer debt. COD cash is never cleared here."""
    if order.service_type != "DELIVERY":
        return
    order.delivery_status = "CANCELLED"
    if order.payment_arrangement != "CREDIT":
        return
    sale = latest_sale(db, order.id)
    if sale is None or sale.due_balance_cents <= 0 or sale.customer_id is None:
        return
    customer = db.get(Customer, sale.customer_id)
    if customer is None:
        return
    ledger_service.credit_return(
        db,
        customer,
        sale,
        return_id=order.id,
        refund_cents=sale.due_balance_cents,
        user_id=user_id,
    )


def _order_for_write(
    db: Session, principal, order_id: uuid.UUID, revision: int, user_id: uuid.UUID | None
) -> tuple[OpenOrder, User]:
    from app.services.order_service import _actor, _writable

    order = _writable(db, principal, order_id, revision)
    if order.service_type != "DELIVERY":
        raise ApiError(422, "not_delivery", "This action is only for a delivery order.")
    actor = _actor(db, principal, user_id, order.store_id)
    return order, actor


def _save(db: Session, order: OpenOrder, actor: User, action: str, details: dict) -> None:
    from app.services.order_service import _touch, orders_out

    audit.record(
        db,
        action_type="UPDATE",
        action=action,
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details=details,
    )
    _touch(order)
    db.commit()
    db.refresh(order)
    return orders_out(db, [order])[0]


def assign_rider(
    db: Session,
    principal,
    order_id: uuid.UUID,
    *,
    revision: int,
    user_id: uuid.UUID | None,
    rider_id: uuid.UUID,
    phone: str | None,
    address: str | None,
):
    order, actor = _order_for_write(db, principal, order_id, revision, user_id)
    if order.delivery_status in ("DELIVERED", "CANCELLED"):
        raise ApiError(409, "delivery_closed", "This delivery can no longer change rider.")
    rider = db.get(User, rider_id)
    if rider is None or not rider.is_active:
        raise ApiError(422, "invalid_request", "Choose a rider who works at this business.")
    if rider.store_id is not None and rider.store_id != order.store_id:
        raise ApiError(403, "store_scope", "That rider is not assigned to this store.")
    order.rider_id = rider.id
    order.delivery_status = "ASSIGNED"
    if phone:
        order.delivery_phone = phone.strip()[:40]
    if address:
        order.delivery_address = address.strip()[:255]
    return _save(db, order, actor, "delivery.assign", {"rider_id": str(rider.id)})


def start_delivery(db: Session, principal, order_id: uuid.UUID, *, revision: int, user_id: uuid.UUID | None):
    order, actor = _order_for_write(db, principal, order_id, revision, user_id)
    if order.rider_id is None:
        raise ApiError(422, "rider_required", "Assign a rider before the delivery starts.")
    if order.delivery_status not in ("ASSIGNED", "PENDING"):
        raise ApiError(409, "delivery_closed", "This delivery has already left or finished.")
    order.delivery_status = "OUT_FOR_DELIVERY"
    return _save(db, order, actor, "delivery.start", {"payment_state": payment_state(order, latest_sale(db, order.id))})


def mark_delivered(
    db: Session,
    principal,
    order_id: uuid.UUID,
    *,
    revision: int,
    user_id: uuid.UUID | None,
    collected_cents: int | None,
):
    """The meal arrived. Reporting what the customer paid the rider does not pay the store."""
    order, actor = _order_for_write(db, principal, order_id, revision, user_id)
    if order.delivery_status == "CANCELLED":
        raise ApiError(409, "delivery_closed", "This delivery was cancelled.")
    if order.delivery_status != "OUT_FOR_DELIVERY":
        raise ApiError(409, "not_out", "Start the delivery before marking it delivered.")
    order.delivery_status = "DELIVERED"
    if collected_cents is not None and order.payment_arrangement == "COD":
        if collected_cents > (order.cod_expected_cents or collected_cents):
            raise ApiError(422, "invalid_request", "The collected amount cannot exceed the order total.")
        order.cod_collected_cents = collected_cents
    finish_delivery(order)
    return _save(
        db,
        order,
        actor,
        "delivery.delivered",
        {
            "payment_state": payment_state(order, latest_sale(db, order.id)),
            "collected_cents": order.cod_collected_cents,
        },
    )


def report_collection(
    db: Session, principal, order_id: uuid.UUID, *, revision: int, user_id: uuid.UUID | None, collected_cents: int
):
    order, actor = _order_for_write(db, principal, order_id, revision, user_id)
    if order.payment_arrangement != "COD":
        raise ApiError(422, "not_cod", "Only a cash-on-delivery order records a rider collection.")
    if collected_cents > order.cod_expected_cents:
        raise ApiError(422, "invalid_request", "The collected amount cannot exceed the order total.")
    order.cod_collected_cents = collected_cents
    return _save(db, order, actor, "delivery.collection", {"collected_cents": collected_cents})


def pending_cod(db: Session, principal, *, store_id: uuid.UUID) -> list:
    from app.services.order_service import _scope, orders_out

    _scope(principal, store_id)
    rows = list(
        db.scalars(
            select(OpenOrder)
            .where(
                OpenOrder.store_id == store_id,
                OpenOrder.service_type == "DELIVERY",
                OpenOrder.payment_arrangement == "COD",
                OpenOrder.status != "VOID",
                OpenOrder.delivery_status.notin_(("CANCELLED",)),
                OpenOrder.cod_handed_cents < OpenOrder.cod_expected_cents,
            )
            .order_by(OpenOrder.opened_at)
        ).all()
    )
    return orders_out(db, rows)


def _variance_approver(
    db: Session, approved_by_id: uuid.UUID | None, *, store_id: uuid.UUID, rider_id: uuid.UUID | None
) -> User:
    """A short count is not written off. A manager with drawer authority has to sign it."""
    if approved_by_id is None:
        raise ApiError(422, "variance_approval", "A short cash handover needs a manager with drawer override.")
    approver = db.get(User, approved_by_id)
    allowed = {Permission.POS_DRAWER_OVERRIDE.value, Permission.POS_SHIFT_MANAGE.value}
    if approver is None or not approver.is_active or not allowed.intersection(approver.permissions):
        raise ApiError(403, "forbidden", "That manager cannot approve a cash discrepancy.")
    if approver.store_id is not None and approver.store_id != store_id:
        raise ApiError(403, "store_scope", "That manager is not assigned to this store.")
    if rider_id is not None and approver.id == rider_id:
        raise ApiError(403, "forbidden", "The rider cannot approve their own cash discrepancy.")
    return approver


def set_outcome(
    db: Session,
    principal,
    order_id: uuid.UUID,
    *,
    revision: int,
    user_id: uuid.UUID | None,
    status: str,
    reason: str,
):
    """The trip failed or came back. Money already recorded stays recorded."""
    order, actor = _order_for_write(db, principal, order_id, revision, user_id)
    if order.delivery_status == "CANCELLED":
        raise ApiError(409, "delivery_closed", "This delivery was cancelled.")
    if status == "FAILED" and order.delivery_status not in (None, "PENDING", "ASSIGNED", "OUT_FOR_DELIVERY"):
        raise ApiError(409, "delivery_closed", "A delivered order is returned, not failed.")
    if status == "RETURNED" and order.delivery_status not in ("OUT_FOR_DELIVERY", "DELIVERED"):
        raise ApiError(409, "not_out", "Only a delivery that has left can be returned.")
    order.delivery_status = status
    return _save(db, order, actor, "delivery.outcome", {"status": status, "reason": reason.strip()[:160]})


def handover(
    db: Session,
    principal,
    order_id: uuid.UUID,
    *,
    revision: int,
    user_id: uuid.UUID | None,
    shift_id: uuid.UUID,
    received_cents: int,
    idempotency_key: str,
    note: str,
    approved_by_id: uuid.UUID | None = None,
):
    """Move rider cash into the open register. A repeated key does not count the cash twice."""
    from app.services.order_service import _actor, _touch, _writable, orders_out

    existing = db.scalar(select(CodHandover).where(CodHandover.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.order_id != order_id:
            raise ApiError(409, "idempotency_conflict", "That handover key was already used for another order.")
        order = db.get(OpenOrder, order_id)
        return orders_out(db, [order])[0]

    order = _writable(db, principal, order_id, revision)
    actor = _actor(db, principal, user_id, order.store_id)
    if order.service_type != "DELIVERY" or order.payment_arrangement != "COD":
        raise ApiError(422, "not_cod", "This order is not waiting for a cash-on-delivery handover.")
    if order.rider_id is not None and actor.id == order.rider_id:
        raise ApiError(403, "forbidden", "The rider cannot confirm their own cash handover.")
    sale = latest_sale(db, order.id)
    if sale is None:
        raise ApiError(422, "not_cod", "Record the delivery sale before accepting rider cash.")
    shift = db.get(RegisterShift, shift_id)
    if shift is None or shift.status != "OPEN" or shift.store_id != order.store_id:
        raise ApiError(422, "shift_required", "Open this store's register shift before accepting rider cash.")
    if shift.currency != sale.currency:
        raise ApiError(422, "invalid_request", "The shift currency does not match the sale.")
    outstanding = order.cod_expected_cents - order.cod_handed_cents
    if received_cents > outstanding:
        raise ApiError(422, "invalid_request", "You cannot accept more cash than the order still owes.")
    approver = None
    if received_cents < outstanding:
        approver = _variance_approver(db, approved_by_id, store_id=order.store_id, rider_id=order.rider_id)
    sale.amount_paid_cents += received_cents
    sale.due_balance_cents -= received_cents
    sale.payment_status = "PAID" if sale.due_balance_cents == 0 else "COD_PARTIAL"
    order.cod_handed_cents += received_cents
    if sale.due_balance_cents == 0:
        mark_lines_paid(order, sale.id)
        finish_delivery(order)
    movement = CashMovement(
        id=uuid.uuid4(),
        shift_id=shift.id,
        store_id=order.store_id,
        user_id=actor.id,
        kind="PAY_IN",
        amount_cents=received_cents,
        currency=sale.currency,
        reason=f"COD handover for order {order.number}"[:250],
        occurred_at=datetime.now(UTC),
    )
    row = CodHandover(
        order_id=order.id,
        sale_id=sale.id,
        store_id=order.store_id,
        rider_id=order.rider_id,
        cashier_id=actor.id,
        approved_by_id=approver.id if approver is not None else None,
        shift_id=shift.id,
        expected_cents=order.cod_expected_cents,
        collected_cents=order.cod_collected_cents,
        received_cents=received_cents,
        outstanding_after_cents=order.cod_expected_cents - order.cod_handed_cents,
        idempotency_key=idempotency_key,
        note=note.strip()[:255],
    )
    db.add(movement)
    db.add(row)
    audit.record(
        db,
        action_type="UPDATE",
        action="delivery.handover",
        target_entity="OpenOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={
            "received_cents": received_cents,
            "outstanding_cents": row.outstanding_after_cents,
            "shift_id": str(shift.id),
            "rider_id": str(order.rider_id) if order.rider_id else None,
            "sale_id": str(sale.id),
            "approved_by_id": str(approver.id) if approver is not None else None,
            "variance_cents": outstanding - received_cents,
        },
    )
    _touch(order)
    db.commit()
    db.refresh(order)
    return orders_out(db, [order])[0]


def live_delivery_items(order: OpenOrder) -> list[OpenOrderItem]:
    return [item for item in order.items if item.voided_at is None]
