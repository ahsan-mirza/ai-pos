"""Sales Insights reads completed receipts. Voided sales stay out of the totals."""

import uuid
from types import SimpleNamespace

from tests.test_returns import (
    CABLE_ID,
    CASHIER_ID,
    STORE_ID,
    admin_id,
    admin_token,
    approval,
    bearer,
    device,
    push,
    receipt,
    record_sale,
    return_payload,
    seed_catalog,
)

from app.core.errors import ApiError
from app.models.sale import Sale
from app.routers.v1.sales_insights import _cell
from app.services.sales_insights import resolve_store

WINDOW = {"start": "2026-10-01T00:00:00Z", "end": "2026-10-20T00:00:00Z"}


def test_completed_sale_reconciles_and_a_void_does_not(client, session) -> None:
    seed_catalog(client)
    sold = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    voided = record_sale(client, product_id=CABLE_ID, price=1500, quantity=1)
    row = session.get(Sale, uuid.UUID(voided["id"]))
    assert row is not None
    row.status = "voided"
    session.commit()

    headers = bearer(admin_token(client))
    summary = client.get("/api/v1/sales-insights/summary", headers=headers, params=WINDOW)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["transactions"] == 1
    assert body["items_sold"] == 2
    assert body["gross_sales_cents"] == 3000
    assert body["tax_cents"] == sold["tax_cents"]
    assert body["charged_cents"] == sold["total_cents"]
    assert body["discount_cents"] == 0
    assert body["refund_cents"] == 0
    assert body["net_sales_cents"] == sold["total_cents"]
    assert body["voided"] == 1
    assert body["average_transaction_cents"] == sold["total_cents"]
    assert body["window"]["timezone"] == "UTC"

    products = client.get("/api/v1/sales-insights/products", headers=headers, params=WINDOW)
    assert products.status_code == 200, products.text
    assert products.json()[0]["name"] == "USB-C Cable"
    assert products.json()[0]["quantity"] == 2
    assert products.json()[0]["sku"] == "ACC-CABLE-USBC"
    assert "cost_cents" in products.json()[0]

    staff = client.get("/api/v1/sales-insights/staff", headers=headers, params=WINDOW)
    assert staff.json()[0]["name"] == "Front Cashier"
    assert staff.json()[0]["transactions"] == 1
    assert staff.json()[0]["net_cents"] == sold["total_cents"]

    payments = client.get("/api/v1/sales-insights/payments", headers=headers, params=WINDOW)
    assert payments.json() == [{"method": "cash", "amount_cents": sold["total_cents"], "transactions": 1}]

    exported = client.get("/api/v1/sales-insights/export.csv", headers=headers, params={**WINDOW, "report": "products"})
    assert exported.status_code == 200
    assert "USB-C Cable" in exported.text
    assert exported.headers["content-type"].startswith("text/csv")


def test_split_tenders_are_not_counted_twice(client) -> None:
    seed_catalog(client)
    sale_id = str(uuid.uuid4())
    payload = {
        "id": sale_id,
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": 3000,
        "tax_cents": 150,
        "total_cents": 3150,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": CABLE_ID,
                "quantity": 2,
                "unit_price_cents": 1500,
                "tax_cents": 150,
                "line_total_cents": 3150,
            }
        ],
        "tenders": [
            {"method": "cash", "amount_cents": 1000},
            {"method": "card", "amount_cents": 2150},
        ],
    }
    assert push(client, "sale", payload).status_code == 200
    headers = bearer(admin_token(client))
    summary = client.get("/api/v1/sales-insights/summary", headers=headers, params=WINDOW)
    assert summary.json()["charged_cents"] == 3150
    payments = client.get("/api/v1/sales-insights/payments", headers=headers, params=WINDOW).json()
    assert sum(row["amount_cents"] for row in payments) == 3150
    assert {row["method"]: row["amount_cents"] for row in payments} == {"cash": 1000, "card": 2150}


def test_a_partial_refund_reduces_net_and_items(client) -> None:
    seed_catalog(client)
    sold = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    body = receipt(client, sold["id"])
    posted = push(client, "sale_return", return_payload(body, override=approval(admin_id(client))))
    assert posted.status_code == 200, posted.text
    headers = bearer(admin_token(client))
    summary = client.get(
        "/api/v1/sales-insights/summary",
        headers=headers,
        params={"start": "2026-10-01T00:00:00Z", "end": "2026-11-06T00:00:00Z"},
    )
    assert summary.status_code == 200, summary.text
    report = summary.json()
    assert report["transactions"] == 1
    assert report["charged_cents"] == sold["total_cents"]
    assert report["refund_cents"] > 0
    assert report["net_sales_cents"] == report["charged_cents"] - report["refund_cents"]
    assert report["items_sold"] == 1


def test_cashier_and_bad_range_are_rejected(client) -> None:
    seed_catalog(client)
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    denied = client.get("/api/v1/sales-insights/summary", headers=bearer(cashier.json()["access_token"]), params=WINDOW)
    assert denied.status_code == 403

    headers = bearer(admin_token(client))
    backwards = client.get(
        "/api/v1/sales-insights/summary",
        headers=headers,
        params={"start": "2026-10-20T00:00:00Z", "end": "2026-10-01T00:00:00Z"},
    )
    assert backwards.status_code == 422
    hourly = client.get("/api/v1/sales-insights/trends", headers=headers, params={**WINDOW, "bucket": "hour"})
    assert hourly.status_code == 422


def test_store_scope_and_formula_guard() -> None:
    try:
        resolve_store(SimpleNamespace(store_id=uuid.UUID(STORE_ID)), uuid.uuid4())
    except ApiError as error:
        assert error.status_code == 403
        assert error.code == "store_scope"
    else:
        raise AssertionError("a store-bound user must not query another branch")
    assert _cell("=HYPERLINK") == "'=HYPERLINK"
    assert _cell("USB-C Cable") == "USB-C Cable"
