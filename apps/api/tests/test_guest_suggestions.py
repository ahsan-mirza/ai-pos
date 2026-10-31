import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session
from tests.test_returns import CASHIER_ID, STORE_ID, admin_token, bearer, device, seed_catalog

from app.models.customer import Customer
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem

GROUP_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")
OPTION_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c2")
OAT = [
    {
        "group_id": str(GROUP_ID),
        "option_id": str(OPTION_ID),
        "group": "Milk",
        "option": "oat milk",
        "price_delta_cents": 200,
    }
]


def profile(client, name: str) -> None:
    token = admin_token(client)
    switched = client.put("/api/v1/settings/profile", headers=bearer(token), json={"business_profile": name})
    assert switched.status_code == 200, switched.text


def dish(session: Session, name: str, category: str, *, days_old: int) -> Product:
    row = Product(
        sku=name.upper().replace(" ", "-"),
        barcode=str(uuid.uuid4().int)[:13],
        name=name,
        category=category,
        price_cents=1800,
        currency="USD",
        item_type="MADE_TO_ORDER",
        is_stock_tracked=False,
    )
    row.created_at = datetime.now(UTC) - timedelta(days=days_old)
    session.add(row)
    session.flush()
    return row


def visit(session: Session, customer: Customer, product: Product, modifiers: list | None = None) -> None:
    sale = Sale(
        store_id=uuid.UUID(STORE_ID),
        cashier_id=uuid.UUID(CASHIER_ID),
        status="completed",
        currency="USD",
        payment_method="cash",
        subtotal_cents=product.price_cents,
        tax_cents=0,
        total_cents=product.price_cents,
        client_sale_id=str(uuid.uuid4()),
        customer_id=customer.id,
        amount_paid_cents=product.price_cents,
        due_balance_cents=0,
    )
    sale.items.append(
        SaleItem(
            product_id=product.id,
            quantity=1,
            unit_price_cents=product.price_cents,
            tax_cents=0,
            line_total_cents=product.price_cents,
            modifiers=modifiers,
        )
    )
    session.add(sale)


def ask(client, **params: str) -> dict:
    response = client.get("/api/v1/orders/suggestions", headers=device(), params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_guests_usual_dish_ranks_first_and_a_new_one_in_that_course_follows(client, session: Session) -> None:
    seed_catalog(client)
    profile(client, "restaurant")
    customer = Customer(code="G-NOOR", name="Noor Ali")
    session.add(customer)
    session.flush()
    latte = dish(session, "Oat latte", "Drinks", days_old=40)
    burger = dish(session, "House burger", "Mains", days_old=40)
    fresh = dish(session, "Iced cardamom", "Drinks", days_old=2)
    for _ in range(4):
        visit(session, customer, latte, OAT)
    for _ in range(2):
        visit(session, customer, burger)
    session.commit()

    body = ask(client, store_id=STORE_ID, customer_id=str(customer.id), product_id=str(burger.id))
    suggestions = body["suggestions"]
    assert suggestions[0]["product_id"] == str(latte.id)
    assert suggestions[0]["kind"] == "usual"
    assert "4 of the last 6 visits" in suggestions[0]["pitch"]
    assert "oat milk" in suggestions[0]["pitch"]
    assert suggestions[0]["modifiers"][0]["option_id"] == str(OPTION_ID)
    assert str(fresh.id) in {item["product_id"] for item in suggestions}
    assert any(item["kind"] == "new" and "Beverages" in item["pitch"] for item in suggestions)
    assert str(burger.id) not in {item["product_id"] for item in suggestions}


def test_a_walk_in_hears_about_a_new_dish_without_a_personal_history(client, session: Session) -> None:
    seed_catalog(client)
    profile(client, "cafe")
    burger = dish(session, "House burger", "Mains", days_old=40)
    tart = dish(session, "Yuzu tart", "Desserts", days_old=1)
    session.commit()

    body = ask(client, store_id=STORE_ID, product_id=str(burger.id))
    suggestions = body["suggestions"]
    fresh = next(item for item in suggestions if item["product_id"] == str(tart.id))
    assert fresh["kind"] == "new"
    assert "Dessert" in fresh["pitch"]
    assert "visit" not in fresh["pitch"].lower()
    assert "usually" not in fresh["pitch"].lower()
    assert all("visit" not in item["pitch"].lower() for item in suggestions)


def test_electronics_and_quick_service_are_refused(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    denied = client.get("/api/v1/orders/suggestions", headers=device(), params={"store_id": STORE_ID})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "capability_disabled"
    blocked = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": "electronics_wholesale", "capabilities": ["open_orders"]},
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "module_not_available"

    switched = client.put(
        "/api/v1/settings/profile", headers=bearer(token), json={"business_profile": "quick_service"}
    )
    assert switched.status_code == 200, switched.text
    denied = client.get("/api/v1/orders/suggestions", headers=device(), params={"store_id": STORE_ID})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"
