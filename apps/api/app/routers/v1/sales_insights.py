"""Tenant sales insights. The caller is the authenticated tenant; a store-bound user cannot pick another branch."""

import csv
import io
import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.sales_insights import (
    CategoryPerformance,
    PaymentSlice,
    ProductPerformance,
    SalesSummary,
    StaffPerformance,
    TransactionRow,
    TrendPoint,
)
from app.services import sales_insights

router = APIRouter()
Reader = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
Bucket = Literal["hour", "day"]
ReportName = Literal["products", "staff", "categories", "payments", "transactions"]


def _filters(
    db: Session,
    principal: Principal,
    start: datetime | None,
    end: datetime | None,
    store_id: uuid.UUID | None,
    cashier_id: uuid.UUID | None,
    category: str | None,
    method: str | None,
    sale_type: str | None,
    status: str | None,
    query: str | None,
) -> sales_insights.InsightFilters:
    begin, finish = sales_insights.window_for(start, end)
    if status is not None and status not in {"completed", "partially_refunded", "refunded", "voided"}:
        status = None
    return sales_insights.InsightFilters(
        start=begin,
        end=finish,
        store_id=sales_insights.resolve_store(principal, store_id),
        cashier_id=cashier_id,
        category=category or None,
        method=method or None,
        sale_type=sale_type or None,
        status=status,
        query=query or None,
        currency=sales_insights.currency_for(db),
    )


def _cell(value: object) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return f"'{text}"
    return text


@router.get("/summary", response_model=SalesSummary)
def sales_summary(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> SalesSummary:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, method, sale_type, status, q)
    return sales_insights.summary(db, filters)


@router.get("/products", response_model=list[ProductPerformance], response_model_exclude_none=True)
def product_performance(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ProductPerformance]:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, method, sale_type, status, q)
    _, rows = sales_insights.products(
        db, filters, include_cost=sales_insights.sees_cost(principal), limit=limit, offset=offset
    )
    return rows


@router.get("/staff", response_model=list[StaffPerformance])
def staff_performance(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[StaffPerformance]:
    filters = _filters(db, principal, start, end, store_id, None, category, method, sale_type, status, q)
    return sales_insights.staff(db, filters)


@router.get("/categories", response_model=list[CategoryPerformance])
def category_performance(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[CategoryPerformance]:
    filters = _filters(db, principal, start, end, store_id, cashier_id, None, method, sale_type, status, q)
    return sales_insights.categories(db, filters)


@router.get("/payments", response_model=list[PaymentSlice])
def payment_analysis(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[PaymentSlice]:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, None, sale_type, status, q)
    return sales_insights.payments(db, filters)


@router.get("/trends", response_model=list[TrendPoint])
def sales_trends(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    bucket: Bucket = "day",
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> list[TrendPoint]:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, method, sale_type, status, q)
    return sales_insights.trends(db, filters, bucket)


@router.get("/transactions", response_model=list[TransactionRow])
def transaction_list(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
    receipt: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionRow]:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, method, sale_type, status, q)
    _, rows = sales_insights.transactions(db, filters, limit=limit, offset=offset, receipt=receipt)
    return rows


@router.get("/export.csv")
def export_csv(
    db: Annotated[Session, Depends(get_db)],
    principal: Reader,
    report: ReportName,
    start: datetime | None = None,
    end: datetime | None = None,
    store_id: uuid.UUID | None = None,
    cashier_id: uuid.UUID | None = None,
    category: str | None = None,
    method: str | None = None,
    sale_type: str | None = None,
    status: str | None = None,
    q: str | None = None,
) -> Response:
    filters = _filters(db, principal, start, end, store_id, cashier_id, category, method, sale_type, status, q)
    include_cost = sales_insights.sees_cost(principal)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if report == "products":
        _, rows = sales_insights.products(db, filters, include_cost=include_cost, limit=5000, offset=0)
        header = ["Product", "SKU", "Category", "Qty", "Gross cents", "Discount cents", "Net cents", "Transactions"]
        if include_cost:
            header.append("Cost cents")
        writer.writerow(header)
        for row in rows:
            values = [
                row.name,
                row.sku,
                row.category,
                row.quantity,
                row.gross_cents,
                row.discount_cents,
                row.net_cents,
                row.transactions,
            ]
            if include_cost:
                values.append(row.cost_cents if row.cost_cents is not None else "")
            writer.writerow([_cell(value) for value in values])
    elif report == "staff":
        writer.writerow(
            ["Staff", "Transactions", "Items", "Gross cents", "Discount cents", "Net cents", "Average cents"]
        )
        for row in sales_insights.staff(db, filters):
            writer.writerow(
                [
                    _cell(value)
                    for value in (
                        row.name,
                        row.transactions,
                        row.items_sold,
                        row.gross_cents,
                        row.discount_cents,
                        row.net_cents,
                        row.average_cents,
                    )
                ]
            )
    elif report == "categories":
        writer.writerow(["Category", "Qty", "Net cents", "Transactions", "Contribution bps"])
        for row in sales_insights.categories(db, filters):
            writer.writerow(
                [
                    _cell(value)
                    for value in (row.category, row.quantity, row.net_cents, row.transactions, row.contribution_bps)
                ]
            )
    elif report == "payments":
        writer.writerow(["Method", "Amount cents", "Transactions"])
        for row in sales_insights.payments(db, filters):
            writer.writerow([_cell(value) for value in (row.method, row.amount_cents, row.transactions)])
    else:
        _, rows = sales_insights.transactions(db, filters, limit=5000, offset=0, receipt=None)
        writer.writerow(
            [
                "Receipt",
                "When",
                "Cashier",
                "Items",
                "Gross cents",
                "Discount cents",
                "Net cents",
                "Tax cents",
                "Payment",
                "Status",
            ]
        )
        for row in rows:
            writer.writerow([
                _cell(value)
                for value in (
                    row.invoice_number or row.id,
                    row.created_at.isoformat(),
                    row.cashier,
                    row.items,
                    row.gross_cents,
                    row.discount_cents,
                    row.net_cents,
                    row.tax_cents,
                    row.payment_method,
                    row.status,
                )
            ])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="sales-{report}.csv"'},
    )
