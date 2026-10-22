from sqlalchemy import select

from app.models.audit_log import AuditLog
from wholesale_support import (
    CABLE,
    admin,
    create_customer,
    device,
    event,
    line,
    push,
    sale,
    seed,
    set_cable_tiers,
)


def test_product_out_exposes_tiers_and_units(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_cable_tiers(client, headers)
    product = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert product["sellable_units"] == ["PIECE", "BOX_10"]
    tier = product["prices"][0]
    assert tier["price_tier"] == "TIER_1"
    assert tier["volume_discounts"] == [{"min_qty": 25, "price_cents": 1000}]


def test_wholesale_split_tender_books_balance_on_account(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_cable_tiers(client, headers)
    customer = create_customer(client, headers)
    body = sale(
        [line(CABLE, 30, 1000, unit_type="BOX_10")],
        sale_type="WHOLESALE",
        customer_id=customer["id"],
        payment_method="on_account",
        tenders=[
            {"method": "cash", "amount_cents": 10_000},
            {"method": "on_account", "amount_cents": 20_000},
        ],
    )
    response = push(client, [event("ws-sale-split", "sale", body)])
    assert response.status_code == 200, response.text

    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert stored["payment_status"] == "PARTIAL"
    assert (stored["amount_paid_cents"], stored["due_balance_cents"]) == (10_000, 20_000)
    assert stored["items"][0]["unit_type"] == "BOX_10"
    assert {tender["method"] for tender in stored["tenders"]} == {"cash", "on_account"}

    refreshed = client.get(f"/api/v1/customers/{customer['id']}", headers=headers).json()
    assert refreshed["current_balance_cents"] == 20_000
    assert refreshed["available_credit_cents"] == 30_000
    assert refreshed["open_invoice_count"] == 1

    stock = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert stock["stock_quantity"] == 470


def test_on_account_needs_wholesale_customer(client) -> None:
    seed(client)
    body = sale(
        [line(CABLE, 1, 1500)],
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 1500}],
    )
    response = push(client, [event("ws-no-customer", "sale", body)])
    assert response.status_code == 422
    assert "wholesale customer" in response.json()["error"]["message"]


def test_price_override_requires_manager(client, session) -> None:
    seed(client)
    headers, admin_id = admin(client)
    blocked = push(client, [event("ws-override-missing", "sale", sale([line(CABLE, 2, 1100, listed=1500)]))])
    assert blocked.status_code == 422
    assert "manager must approve" in blocked.json()["error"]["message"]

    approved = sale([line(CABLE, 2, 1100, listed=1500, override_by=admin_id)])
    response = push(client, [event("ws-override-ok", "sale", approved)])
    assert response.status_code == 200, response.text
    stored = client.get(f"/api/v1/sales/{approved['id']}", headers=device()).json()
    assert stored["items"][0]["price_override_by_id"] == admin_id
    logs = session.scalars(select(AuditLog).where(AuditLog.action == "sale.price_override")).all()
    assert len(logs) == 1 and str(logs[0].approver_id) == admin_id


def test_over_credit_limit_is_accepted_and_audited(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=1000)
    body = sale(
        [line(CABLE, 2, 1500)],
        customer_id=customer["id"],
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 3000}],
    )
    response = push(client, [event("ws-over-limit", "sale", body)])
    assert response.status_code == 200, response.text
    logs = session.scalars(select(AuditLog).where(AuditLog.action == "sale.credit_limit_exceeded")).all()
    assert len(logs) == 1
    assert logs[0].details["balance_after_cents"] == 3000


def test_tenders_must_cover_total(client) -> None:
    seed(client)
    body = sale([line(CABLE, 2, 1500)], tenders=[{"method": "cash", "amount_cents": 1000}])
    response = push(client, [event("ws-short-tender", "sale", body)])
    assert response.status_code == 422


def test_retail_sale_without_new_fields_still_works(client) -> None:
    seed(client)
    body = sale([line(CABLE, 1, 1500)])
    for item in body["items"]:
        item.pop("unit_type")
        item.pop("list_price_cents")
    response = push(client, [event("ws-legacy", "sale", body)])
    assert response.status_code == 200, response.text
    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert stored["payment_status"] == "PAID"
    assert [(t["method"], t["amount_cents"]) for t in stored["tenders"]] == [("cash", 1500)]
    assert stored["invoice_number"] == "DT-01-S-000001"
