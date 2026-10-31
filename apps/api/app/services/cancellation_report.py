"""Cancellation figures read from sales orders, open orders, and the audit log.

Cancelled amounts are never added to completed sales. A fully cancelled order and a
partial line cancellation are counted separately.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.product import Product
from app.models.restaurant import OpenOrder, OpenOrderItem
from app.models.sales_order import SalesOrder, SalesOrderLine

# Code -> (who started it, label). "other" is the fallback for free text.
REASON_CODES: dict[str, tuple[str, str]] = {
    "changed_mind": ("customer", "Customer changed mind"),
    "duplicate": ("customer", "Duplicate order"),
    "wrong_item": ("employee", "Incorrect product or service"),
    "wrong_quantity": ("employee", "Incorrect quantity"),
    "price": ("customer", "Price or promotion issue"),
    "stock": ("business", "Stock unavailable"),
    "payment": ("payment", "Payment failure"),
    "prep_delay": ("business", "Preparation delay"),
    "delivery": ("fulfillment", "Delivery issue"),
    "unavailable": ("customer", "Customer unavailable"),
    "entry_mistake": ("employee", "Employee mistake"),
    "operational": ("business", "Operational issue"),
    "other": ("employee", "Other"),
}

_CODED = re.compile(r"^\[([a-z_]+)\]\s*(.*)$", re.DOTALL)
CANCEL_ACTIONS = ("sales_order.cancelled", "sales_order.cancel_lines", "order.void", "order.void_sent_item")


def classify(reason: str | None) -> tuple[str, str, str]:
    """Return reason code, initiator, and the note without the code prefix."""
    text = (reason or "").strip()
    match = _CODED.match(text)
    code = match.group(1) if match is not None and match.group(1) in REASON_CODES else "other"
    note = (match.group(2) if match is not None and match.group(1) in REASON_CODES else text).strip()
    initiator, _label = REASON_CODES[code]
    return code, initiator, note


def rates(created: int, full: int, partial: int) -> tuple[float, float]:
    """Full-order rate and partial-order rate, each against orders created in the window."""
    if created <= 0:
        return 0.0, 0.0
    return round(100 * full / created, 1), round(100 * partial / created, 1)


def _window(start: date, end: date) -> tuple[datetime, datetime]:
    opening = datetime.combine(start, time.min, UTC)
    closing = datetime.combine(end + timedelta(days=1), time.min, UTC)
    return opening, closing


def _count(db: Session, query) -> int:
    return int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)


def _latest_audits(db: Session, entity: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, AuditLog]:
    if not ids:
        return {}
    found: dict[uuid.UUID, AuditLog] = {}
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.target_entity == entity,
            AuditLog.target_entity_id.in_(ids),
            AuditLog.action.in_(CANCEL_ACTIONS),
        )
        .order_by(AuditLog.occurred_at.desc())
    )
    for entry in rows:
        if entry.target_entity_id is not None and entry.target_entity_id not in found:
            found[entry.target_entity_id] = entry
    return found


def build(
    db: Session,
    *,
    start: date,
    end: date,
    store_id: uuid.UUID | None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, object]:
    opening, closing = _window(start, end)

    def sales_created():
        query = select(SalesOrder.id).where(SalesOrder.created_at >= opening, SalesOrder.created_at < closing)
        return query.where(SalesOrder.store_id == store_id) if store_id is not None else query

    def tabs_created():
        query = select(OpenOrder.id).where(OpenOrder.opened_at >= opening, OpenOrder.opened_at < closing)
        return query.where(OpenOrder.store_id == store_id) if store_id is not None else query

    created = _count(db, sales_created()) + _count(db, tabs_created())
    cancelled_line = select(SalesOrderLine.order_id).where(SalesOrderLine.quantity_cancelled > 0)
    voided_line = select(OpenOrderItem.order_id).where(OpenOrderItem.voided_at.is_not(None))
    sales_hit = select(SalesOrder).where(
        SalesOrder.id.in_(sales_created()),
        or_(SalesOrder.status == "CANCELLED", SalesOrder.id.in_(cancelled_line)),
    )
    tabs_hit = select(OpenOrder).where(
        OpenOrder.id.in_(tabs_created()),
        or_(OpenOrder.status == "VOID", OpenOrder.id.in_(voided_line)),
    )
    full_sales = _count(db, sales_created().where(SalesOrder.status == "CANCELLED"))
    partial_sales = _count(
        db, sales_created().where(SalesOrder.status != "CANCELLED", SalesOrder.id.in_(cancelled_line))
    )
    full_tabs = _count(db, tabs_created().where(OpenOrder.status == "VOID"))
    partial_tabs = _count(db, tabs_created().where(OpenOrder.status != "VOID", OpenOrder.id.in_(voided_line)))
    full_count = full_sales + full_tabs
    partial_count = partial_sales + partial_tabs
    full_rate, partial_rate = rates(created, full_count, partial_count)

    sales_orders = list(db.scalars(sales_hit))
    tab_orders = list(db.scalars(tabs_hit))
    sales_audit = _latest_audits(db, "SalesOrder", [order.id for order in sales_orders])
    tab_audit = _latest_audits(db, "OpenOrder", [order.id for order in tab_orders])
    product_ids = {item.product_id for order in tab_orders for item in order.items if item.voided_at is not None}
    names = {}
    if product_ids:
        names = {row.id: row.name for row in db.scalars(select(Product).where(Product.id.in_(product_ids)))}

    rows: list[dict[str, object]] = []
    reason_counts: dict[str, int] = {code: 0 for code in REASON_CODES}
    customer_count = 0
    employee_count = 0
    cancelled_value = 0
    hours: list[float] = []

    def add_row(
        *,
        kind: str,
        order_id: uuid.UUID,
        number: str,
        store: uuid.UUID,
        order_type: str,
        created_at: datetime,
        cancelled_at: datetime | None,
        full: bool,
        value: int,
        audit: AuditLog | None,
        fallback: str | None,
        items: list[dict[str, object]],
    ) -> None:
        nonlocal customer_count, employee_count, cancelled_value
        code, initiator, note = classify(audit.reason_notes if audit is not None and audit.reason_notes else fallback)
        reason_counts[code] = reason_counts.get(code, 0) + 1
        if initiator == "customer":
            customer_count += 1
        else:
            employee_count += 1
        cancelled_value += value
        if cancelled_at is not None:
            hours.append(max(0.0, (cancelled_at - created_at).total_seconds() / 3600))
        rows.append(
            {
                "kind": kind,
                "order_id": order_id,
                "number": number,
                "store_id": store,
                "order_type": order_type,
                "full": full,
                "status": "cancelled" if full else "partially_cancelled",
                "reason_code": code,
                "reason_label": REASON_CODES[code][1],
                "initiator": initiator,
                "note": note,
                "cancelled_value_cents": value,
                "created_at": created_at,
                "cancelled_at": cancelled_at,
                "employee_name": audit.user_name if audit is not None else None,
                "employee_role": audit.user_role if audit is not None else None,
                "approver_id": audit.approver_id if audit is not None else None,
                "items": items,
            }
        )

    for order in sales_orders:
        full = order.status == "CANCELLED"
        if not full and not any(line.quantity_cancelled for line in order.lines):
            continue
        add_row(
            kind="sales_order",
            order_id=order.id,
            number=order.number,
            store=order.store_id,
            order_type=order.sale_type,
            created_at=order.created_at,
            cancelled_at=order.closed_at,
            full=full,
            value=sum(line.quantity_cancelled * line.unit_price_cents for line in order.lines),
            audit=sales_audit.get(order.id),
            fallback=None,
            items=[
                {"name": line.description or "", "quantity": line.quantity_cancelled, "sku": ""}
                for line in order.lines
                if line.quantity_cancelled
            ],
        )
    for order in tab_orders:
        voided = [item for item in order.items if item.voided_at is not None]
        full = order.status == "VOID"
        if not full and not voided:
            continue
        add_row(
            kind="open_order",
            order_id=order.id,
            number=str(order.number),
            store=order.store_id,
            order_type=order.service_type,
            created_at=order.opened_at,
            cancelled_at=order.closed_at or (voided[0].voided_at if voided else None),
            full=full,
            value=sum(item.quantity * item.unit_price_cents for item in voided),
            audit=tab_audit.get(order.id),
            fallback=voided[0].void_reason if voided else None,
            items=[
                {"name": names.get(item.product_id, ""), "quantity": item.quantity, "sku": ""}
                for item in voided
            ],
        )

    rows.sort(key=lambda row: row["cancelled_at"] or row["created_at"], reverse=True)
    average_hours = round(sum(hours) / len(hours), 1) if hours else None
    return {
        "start": start,
        "end": end,
        "created_orders": created,
        "fully_cancelled": full_count,
        "partially_cancelled": partial_count,
        "full_cancellation_rate": full_rate,
        "partial_cancellation_rate": partial_rate,
        "cancelled_value_cents": cancelled_value,
        "customer_requested": customer_count,
        "employee_initiated": employee_count,
        "average_hours_to_cancel": average_hours,
        "reasons": [
            {"code": code, "label": label, "initiator": initiator, "count": reason_counts[code]}
            for code, (initiator, label) in REASON_CODES.items()
            if reason_counts[code]
        ],
        "total": len(rows),
        "rows": rows[offset : offset + limit],
    }


def cancelled_line_value(db: Session, store_id: uuid.UUID | None) -> int:
    """Sum of cancelled sales-order line value. Used to prove it is not a sales total."""
    query = select(func.coalesce(func.sum(SalesOrderLine.quantity_cancelled * SalesOrderLine.unit_price_cents), 0))
    if store_id is not None:
        query = query.join(SalesOrder, SalesOrder.id == SalesOrderLine.order_id).where(SalesOrder.store_id == store_id)
    return int(db.scalar(query) or 0)
