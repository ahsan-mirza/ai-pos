"""Delivery payment stays independent of kitchen and dispatch."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from tests.test_orders import line, setup
from tests.test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_id, admin_token, bearer, device, push

from app.models.customer import CustomerLedgerEntry
from app.models.restaurant import OpenOrder, OpenOrderItem
from app.models.sale import Sale
from app.models.shift import CashMovement
from app.models.user import User
from wholesale_support import admin, create_customer, event, sale, seed
from wholesale_support import line as wholesale_line
from wholesale_support import push as wholesale_push

TOTAL = 1575  # 1500 plus 5% tax, matching the restaurant catalogue.


def delivery_order(client) -> dict:
    response = client.post(
        "/api/v1/orders",
        headers=device(),
        json={
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "service_type": "DELIVERY",
            "covers": 1,
            "name": "Amina",
            "note": "12 Creek Road",
            "user_id": CASHIER_ID,
            "items": [line()],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def cod_sale(order: dict) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "store_id": STORE_ID,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "payment_method": "cod",
        "subtotal_cents": 1500,
        "tax_cents": 75,
        "total_cents": TOTAL,
        "client_sale_id": str(uuid.uuid4()),
        "order_id": order["id"],
        "order_item_ids": [order["items"][0]["id"]],
        "tenders": [{"method": "cod", "amount_cents": TOTAL}],
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": CABLE_ID,
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_cents": 75,
                "line_total_cents": TOTAL,
            }
        ],
    }
    body["client_sale_id"] = body["id"]
    return body


def open_shift(client) -> str:
    shift_id = str(uuid.uuid4())
    opened = push(
        client,
        "register_shift",
        {
            "id": shift_id,
            "store_id": STORE_ID,
            "opened_by_id": CASHIER_ID,
            "opened_at": datetime.now(UTC).isoformat(),
            "opening_float_cents": 10_000,
            "currency": "USD",
            "status": "OPEN",
        },
    )
    assert opened.status_code == 200, opened.text
    return shift_id


def add_rider(session) -> User:
    cashier = session.get(User, uuid.UUID(CASHIER_ID))
    rider = User(
        id=uuid.uuid4(),
        username=f"rider-{uuid.uuid4().hex[:8]}",
        email=f"rider-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Ravi Rider",
        hashed_pin=cashier.hashed_pin,
        is_active=True,
        store_id=uuid.UUID(STORE_ID),
        role_id=cashier.role_id,
        has_pos_access=True,
        has_portal_access=False,
        failed_login_attempts=0,
        token_version=0,
    )
    session.add(rider)
    session.commit()
    return rider


def test_cod_stays_unpaid_until_the_cashier_accepts_the_cash(client, session) -> None:
    setup(client)
    token = admin_token(client)
    order = delivery_order(client)
    shift_id = open_shift(client)
    recorded = push(client, "sale", {**cod_sale(order), "shift_id": shift_id})
    assert recorded.status_code == 200, recorded.text

    sale = session.scalar(select(Sale).where(Sale.order_id == uuid.UUID(order["id"])))
    assert sale is not None
    assert sale.payment_status == "COD_AWAITING"
    assert sale.amount_paid_cents == 0
    assert sale.due_balance_cents == TOTAL
    assert session.scalar(select(func.count()).select_from(CustomerLedgerEntry)) == 0

    open_row = client.get(f"/api/v1/orders/{order['id']}", headers=device())
    assert open_row.status_code == 200, open_row.text
    body = open_row.json()
    assert body["status"] == "OPEN"
    assert body["payment_arrangement"] == "COD"
    assert body["payment_state"] == "COD_AWAITING_COLLECTION"
    assert body["items"][0]["paid_sale_id"] is None

    rider = add_rider(session)
    assigned = client.post(
        f"/api/v1/orders/{order['id']}/delivery/assign",
        headers=device(),
        json={
            "revision": body["revision"],
            "user_id": CASHIER_ID,
            "rider_id": str(rider.id),
            "phone": "+971500000000",
            "address": "12 Creek Road",
        },
    )
    assert assigned.status_code == 200, assigned.text
    started = client.post(
        f"/api/v1/orders/{order['id']}/delivery/start",
        headers=device(),
        json={"revision": assigned.json()["revision"], "user_id": CASHIER_ID},
    )
    assert started.status_code == 200, started.text
    delivered = client.post(
        f"/api/v1/orders/{order['id']}/delivery/delivered",
        headers=device(),
        json={"revision": started.json()["revision"], "user_id": CASHIER_ID, "collected_cents": TOTAL},
    )
    assert delivered.status_code == 200, delivered.text
    after_drop = delivered.json()
    assert after_drop["delivery_status"] == "DELIVERED"
    assert after_drop["payment_state"] == "COD_AWAITING_HANDOVER"
    assert after_drop["status"] == "OPEN"
    session.expire_all()
    assert session.get(Sale, sale.id).amount_paid_cents == 0

    drawer = client.get(f"/api/v1/shifts/{shift_id}", headers=bearer(token))
    assert drawer.status_code == 200, drawer.text
    assert drawer.json()["expected_cash_cents"] == 10_000

    short = client.post(
        f"/api/v1/orders/{order['id']}/delivery/handover",
        headers=device(),
        json={
            "revision": after_drop["revision"],
            "user_id": CASHIER_ID,
            "shift_id": shift_id,
            "received_cents": 1000,
            "idempotency_key": "cod-short-unapproved",
        },
    )
    assert short.status_code == 422
    assert short.json()["error"]["code"] == "variance_approval"
    refused = client.post(
        f"/api/v1/orders/{order['id']}/delivery/handover",
        headers=device(),
        json={
            "revision": after_drop["revision"],
            "user_id": CASHIER_ID,
            "shift_id": shift_id,
            "received_cents": 1000,
            "idempotency_key": "cod-self-handover",
            "approved_by_id": admin_id(client),
        },
    )
    assert refused.status_code == 200, refused.text
    partial = refused.json()
    assert partial["payment_state"] == "COD_PARTIAL"
    assert partial["cod_handed_cents"] == 1000
    assert partial["status"] == "OPEN"
    session.expire_all()
    assert session.get(Sale, sale.id).due_balance_cents == TOTAL - 1000
    assert session.scalar(select(func.count()).select_from(CashMovement)) == 1

    again = client.post(
        f"/api/v1/orders/{order['id']}/delivery/handover",
        headers=device(),
        json={
            "revision": 1,
            "user_id": CASHIER_ID,
            "shift_id": shift_id,
            "received_cents": 1000,
            "idempotency_key": "cod-self-handover",
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["cod_handed_cents"] == 1000
    assert session.scalar(select(func.count()).select_from(CashMovement)) == 1

    rest = client.post(
        f"/api/v1/orders/{order['id']}/delivery/handover",
        headers=device(),
        json={
            "revision": again.json()["revision"],
            "user_id": CASHIER_ID,
            "shift_id": shift_id,
            "received_cents": TOTAL - 1000,
            "idempotency_key": "cod-rest-handover",
        },
    )
    assert rest.status_code == 200, rest.text
    paid = rest.json()
    assert paid["payment_state"] == "PAID"
    assert paid["status"] == "SETTLED"
    assert paid["cod_handed_cents"] == TOTAL
    drawer = client.get(f"/api/v1/shifts/{shift_id}", headers=bearer(token))
    assert drawer.json()["expected_cash_cents"] == 10_000 + TOTAL
    assert drawer.json()["report"]["tenders"].get("cash", 0) == 0
    assert drawer.json()["report"]["pay_in_cents"] == TOTAL


def test_a_failed_delivery_does_not_collect_payment(client, session) -> None:
    setup(client)
    order = delivery_order(client)
    shift_id = open_shift(client)
    assert push(client, "sale", {**cod_sale(order), "shift_id": shift_id}).status_code == 200
    current = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    failed = client.post(
        f"/api/v1/orders/{order['id']}/delivery/outcome",
        headers=device(),
        json={
            "revision": current["revision"],
            "user_id": CASHIER_ID,
            "status": "FAILED",
            "reason": "Customer unavailable",
        },
    )
    assert failed.status_code == 200, failed.text
    body = failed.json()
    assert body["delivery_status"] == "FAILED"
    assert body["payment_state"] == "COD_AWAITING_COLLECTION"
    assert body["status"] == "OPEN"
    assert body["cod_handed_cents"] == 0
    session.expire_all()
    sale = session.scalar(select(Sale).where(Sale.order_id == uuid.UUID(order["id"])))
    assert sale.payment_status == "COD_AWAITING"
    assert sale.amount_paid_cents == 0
    assert session.scalar(select(func.count()).select_from(CashMovement)) == 0
    returned = client.post(
        f"/api/v1/orders/{order['id']}/delivery/outcome",
        headers=device(),
        json={"revision": body["revision"], "user_id": CASHIER_ID, "status": "RETURNED", "reason": "Brought back"},
    )
    assert returned.status_code == 409


def test_rider_cannot_confirm_their_own_handover(client, session) -> None:
    setup(client)
    order = delivery_order(client)
    shift_id = open_shift(client)
    assert push(client, "sale", {**cod_sale(order), "shift_id": shift_id}).status_code == 200
    current = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assigned = client.post(
        f"/api/v1/orders/{order['id']}/delivery/assign",
        headers=device(),
        json={"revision": current["revision"], "user_id": CASHIER_ID, "rider_id": CASHIER_ID},
    )
    assert assigned.status_code == 200, assigned.text
    refused = client.post(
        f"/api/v1/orders/{order['id']}/delivery/handover",
        headers=device(),
        json={
            "revision": assigned.json()["revision"],
            "user_id": CASHIER_ID,
            "shift_id": shift_id,
            "received_cents": TOTAL,
            "idempotency_key": "rider-cannot-close",
        },
    )
    assert refused.status_code == 403
    assert session.scalar(select(func.count()).select_from(CashMovement)) == 0


def test_paid_delivery_does_not_wait_for_rider_cash(client, session) -> None:
    setup(client)
    order = delivery_order(client)
    paid = dict(cod_sale(order))
    paid["payment_method"] = "cash"
    paid["tenders"] = [{"method": "cash", "amount_cents": TOTAL}]
    assert push(client, "sale", paid).status_code == 200
    body = client.get(f"/api/v1/orders/{order['id']}", headers=device()).json()
    assert body["payment_arrangement"] == "PAID_NOW"
    assert body["payment_state"] == "PAID"
    assert body["status"] == "OPEN"
    assert body["delivery_status"] == "PENDING"
    assert session.scalar(select(Sale).where(Sale.order_id == uuid.UUID(order["id"]))).amount_paid_cents == TOTAL


def test_credit_delivery_posts_a_receivable_and_no_drawer_cash(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    customer = create_customer(client, headers, credit_limit_cents=100_000)
    order_id = uuid.uuid4()
    item_id = uuid.uuid4()
    session.add(
        OpenOrder(
            id=order_id,
            store_id=uuid.UUID(STORE_ID),
            number=1,
            service_type="DELIVERY",
            status="OPEN",
            covers=1,
            name="Amina",
            opened_by_id=uuid.UUID(CASHIER_ID),
        )
    )
    session.flush()
    session.add(
        OpenOrderItem(
            id=item_id,
            order_id=order_id,
            product_id=uuid.UUID(CABLE_ID),
            quantity=1,
            unit_price_cents=1500,
        )
    )
    session.commit()
    body = sale(
        [wholesale_line(CABLE_ID, 1, 1500)],
        customer_id=customer["id"],
        payment_method="on_account",
        tenders=[{"method": "on_account", "amount_cents": 1500}],
        order_id=str(order_id),
        order_item_ids=[str(item_id)],
    )
    recorded = wholesale_push(client, [event("credit-delivery", "sale", body)])
    assert recorded.status_code == 200, recorded.text
    session.expire_all()
    invoice = session.get(Sale, uuid.UUID(body["id"]))
    order = session.get(OpenOrder, order_id)
    assert invoice.payment_status == "ON_ACCOUNT_UNPAID"
    assert invoice.amount_paid_cents == 0
    assert order.payment_arrangement == "CREDIT"
    assert order.status == "OPEN"
    assert order.items[0].paid_sale_id is None
    assert session.scalar(select(func.count()).select_from(CashMovement)) == 0
    assert session.scalar(select(func.sum(CustomerLedgerEntry.amount_cents))) == 1500

    paid = client.post(
        f"/api/v1/customers/{customer['id']}/payments",
        headers=headers,
        json={"amount_cents": 1500, "method": "transfer", "reference": "TRX-DEL"},
    )
    assert paid.status_code == 201, paid.text
    session.expire_all()
    assert session.get(Sale, invoice.id).payment_status == "PAID"
    assert session.get(OpenOrder, order_id).status == "OPEN"
    assert session.scalar(select(func.sum(CustomerLedgerEntry.amount_cents))) == 0
