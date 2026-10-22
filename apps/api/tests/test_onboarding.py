"""Practice mode: sample items, the "First win" checklist, and the one-time Go live reset."""

import uuid
from datetime import date, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.accounting import JournalEntry
from app.models.customer import Customer
from app.models.document_sequence import DocumentSequence
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.sale import Sale
from app.models.serial_number import SerialNumber
from app.services import sample_data
from app.services.settings_service import clear_settings_cache, load_settings
from wholesale_support import CABLE, PHONE, STORE, admin, event, line, push, sale, seed


def _practice(session) -> None:
    row = load_settings(session)
    row.live_at = None
    session.commit()
    clear_settings_cache()
    assert sample_data.load(session, get_settings(), profile="electronics_wholesale", sub_type="electronics_retail")


def _count(session, model, *where) -> int:
    return int(session.scalar(select(func.count()).select_from(model).where(*where)) or 0)


def _on_hand(session, product_id: str) -> int:
    level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(product_id), InventoryLevel.store_id == uuid.UUID(STORE)
        )
    )
    session.refresh(level)
    return level.quantity_on_hand


def test_sample_items_load_once_and_are_flagged(client, session) -> None:
    seed(client)
    _practice(session)
    samples = session.scalars(select(Product).where(Product.is_sample.is_(True))).all()
    assert len(samples) == 6
    serialized = [product for product in samples if product.is_serialized]
    assert (
        serialized
        and _count(
            session,
            SerialNumber,
            SerialNumber.product_id.in_([p.id for p in serialized]),
            SerialNumber.status == "in_stock",
        )
        == 7
    )
    assert _count(session, Customer, Customer.is_sample.is_(True)) == 2
    assert sample_data.load(session, get_settings(), profile="electronics_wholesale") == 0
    headers, _ = admin(client)
    assert client.get("/api/v1/settings", headers=headers).json()["practice_mode"] is True


def test_checklist_tracks_first_wins(client, session) -> None:
    seed(client)
    _practice(session)
    headers, _ = admin(client)
    checklist = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert checklist.status_code == 200, checklist.text
    body = checklist.json()
    done = {item["key"]: item["done"] for item in body["items"]}
    assert body["practice_mode"] is True and body["store_name"] == "Downtown"
    assert done == {
        "test_sale": False,
        "real_product": True,
        "import_stock": False,
        "till": False,
        "cashier": True,
        "go_live": False,
    }
    assert push(client, [event("practice-sale-1", "sale", sale([line(CABLE, 1, 1500)]))]).status_code == 200
    after = client.get("/api/v1/onboarding/checklist", headers=headers).json()
    assert next(item for item in after["items"] if item["key"] == "test_sale")["done"] is True


def test_go_live_wipes_practice_and_restores_stock(client, session) -> None:
    units = seed(client, phone_units=2)
    _practice(session)
    headers, _ = admin(client)
    sample = session.scalar(select(Product).where(Product.is_sample.is_(True), Product.is_serialized.is_(False)))
    orders = [
        sale([line(CABLE, 3, 1500), line(PHONE, 1, 79900, serial=units[0])]),
        sale([line(str(sample.id), 2, sample.price_cents)]),
    ]
    pushed = push(client, [event(f"practice-{index}", "sale", order) for index, order in enumerate(orders)])
    assert pushed.status_code == 200, pushed.text
    assert _on_hand(session, CABLE) == 497 and _on_hand(session, PHONE) == 1
    assert _count(session, DocumentSequence, DocumentSequence.last_value > 0) > 0
    today = date.today()
    vat_period = {"from": str(today - timedelta(days=30)), "to": str(today + timedelta(days=30))}
    assert client.get("/api/v1/reports/vat", headers=headers, params=vat_period).json()["invoices"] == 2

    wrong = client.post("/api/v1/onboarding/go-live", headers=headers, json={"confirm": "Uptown"})
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "confirm_mismatch")

    live = client.post("/api/v1/onboarding/go-live", headers=headers, json={"confirm": " downtown "})
    assert live.status_code == 200, live.text
    assert live.json() | {"live_at": None} == {
        "live_at": None,
        "sales_removed": 2,
        "sample_products_removed": 6,
        "sample_customers_removed": 2,
    }
    session.expire_all()
    assert _on_hand(session, CABLE) == 500 and _on_hand(session, PHONE) == 2
    phones = session.scalars(select(SerialNumber.status).where(SerialNumber.product_id == uuid.UUID(PHONE))).all()
    assert phones == ["in_stock", "in_stock"]
    assert _count(session, Sale) == 0 and _count(session, JournalEntry) == 0
    assert _count(session, StockMovement, StockMovement.reference_type == "sale") == 0
    assert _count(session, Product, Product.is_sample.is_(True)) == 0
    assert _count(session, Customer, Customer.is_sample.is_(True)) == 0
    assert _count(session, DocumentSequence, DocumentSequence.last_value > 0) == 0
    vat = client.get("/api/v1/reports/vat", headers=headers, params=vat_period).json()
    assert (vat["invoices"], vat["output_vat_cents"], vat["net_vat_cents"]) == (0, 0, 0)
    assert client.get("/api/v1/settings", headers=headers).json()["practice_mode"] is False

    again = client.post("/api/v1/onboarding/go-live", headers=headers, json={"confirm": "Downtown"})
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_live")


def test_stores_created_outside_signup_are_already_live(client) -> None:
    seed(client)
    headers, _ = admin(client)
    assert client.get("/api/v1/settings", headers=headers).json()["practice_mode"] is False
    refused = client.post("/api/v1/onboarding/go-live", headers=headers, json={"confirm": "Downtown"})
    assert refused.status_code == 409
