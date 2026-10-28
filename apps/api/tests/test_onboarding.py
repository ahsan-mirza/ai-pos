"""Practice mode: sample items, the "First win" checklist, and the one-time Go live reset."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.accounting import JournalEntry
from app.models.customer import Customer
from app.models.device import Device
from app.models.document_sequence import DocumentSequence
from app.models.einvoice import EInvoiceChain, TaxAuthorityCredential
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.sale import Sale
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.sync_event import SyncEvent
from app.models.user import User
from app.services import sample_data
from app.services.settings_service import clear_settings_cache, load_settings
from wholesale_support import CABLE, PHONE, STORE, admin, create_customer, event, line, push, sale, seed


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


def test_catalogue_step_follows_each_business_type() -> None:
    from app.core.capabilities import FOOD_AND_BEVERAGE, PROFILES
    from app.services.onboarding_service import catalogue_copy

    for profile in PROFILES:
        label, hint, action = catalogue_copy(profile)
        if profile in FOOD_AND_BEVERAGE:
            assert "menu" in label.lower()
            assert action == "Add a menu item"
        else:
            assert "menu" not in label.lower()
            assert action == "Add a product"
        assert hint
    assert "sizes" in catalogue_copy("retail_fashion")[1]
    assert "barcodes" in catalogue_copy("grocery")[1]
    assert "serial numbers" in catalogue_copy("electronics_wholesale")[1]


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


def _go(confirm: str, **extra: object) -> dict:
    body = {"confirm": confirm, "mode": "keep", "opening_stock": "keep", "tax_acknowledged": True}
    body.update(extra)
    return body


def test_checklist_tracks_first_wins(client, session) -> None:
    seed(client)
    _practice(session)
    headers, _ = admin(client)
    checklist = client.get("/api/v1/onboarding/checklist", headers=headers)
    assert checklist.status_code == 200, checklist.text
    body = checklist.json()
    done = {item["key"]: item["done"] for item in body["items"]}
    assert body["practice_mode"] is True and body["store_name"] == "Downtown"
    assert body["opening_stock_units"] == 500
    assert body["version"] == 1
    assert done == {
        "explore": False,
        "configure": False,
        "catalogue": True,
        "practice": False,
        "team": False,
        "activate": False,
    }
    catalogue = next(item for item in body["items"] if item["key"] == "catalogue")
    assert catalogue["label"] == "Add your first products"
    assert "serial numbers" in catalogue["hint"]
    assert push(client, [event("practice-sale-1", "sale", sale([line(CABLE, 1, 1500)]))]).status_code == 200
    after = client.get("/api/v1/onboarding/checklist", headers=headers).json()
    assert next(item for item in after["items"] if item["key"] == "practice")["done"] is True


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

    wrong = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Uptown"))
    assert (wrong.status_code, wrong.json()["error"]["code"]) == (422, "confirm_mismatch")

    live = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go(" downtown "))
    assert live.status_code == 200, live.text
    assert live.json() | {"live_at": None} == {
        "live_at": None,
        "mode": "keep",
        "opening_stock": "keep",
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

    again = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown"))
    assert (again.status_code, again.json()["error"]["code"]) == (409, "already_live")


def test_stores_created_outside_signup_are_already_live(client) -> None:
    seed(client)
    headers, _ = admin(client)
    assert client.get("/api/v1/settings", headers=headers).json()["practice_mode"] is False
    refused = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown"))
    assert refused.status_code == 409


def test_go_live_requires_tax_ack_and_opening_stock(client, session) -> None:
    seed(client)
    _practice(session)
    headers, _ = admin(client)
    missing_tax = client.post(
        "/api/v1/onboarding/go-live",
        headers=headers,
        json={"confirm": "Downtown", "mode": "keep", "opening_stock": "keep"},
    )
    assert (missing_tax.status_code, missing_tax.json()["error"]["code"]) == (422, "tax_not_acknowledged")
    missing_stock = client.post(
        "/api/v1/onboarding/go-live",
        headers=headers,
        json={"confirm": "Downtown", "mode": "keep", "tax_acknowledged": True},
    )
    assert (missing_stock.status_code, missing_stock.json()["error"]["code"]) == (422, "opening_stock_required")


def test_go_live_keep_can_reset_opening_stock(client, session) -> None:
    seed(client, phone_units=2)
    _practice(session)
    headers, _ = admin(client)
    customer = create_customer(client, headers)
    live = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown", opening_stock="reset"))
    assert live.status_code == 200, live.text
    assert live.json()["opening_stock"] == "reset"
    session.expire_all()
    assert _on_hand(session, CABLE) == 0
    assert _count(session, SerialNumber) == 0
    assert session.get(Product, uuid.UUID(CABLE)) is not None
    kept = session.get(Customer, uuid.UUID(customer["id"]))
    assert kept is not None and kept.is_sample is False
    assert _count(session, Product, Product.is_sample.is_(True)) == 0


def test_go_live_fresh_reopens_setup(client, session) -> None:
    seed(client)
    _practice(session)
    headers, admin_id = admin(client)
    row = load_settings(session)
    row.legal_name = "Downtown"
    row.trn = "100000000000003"
    row.onboarded_at = datetime.now(UTC)
    session.add(
        Device(
            store_id=uuid.UUID(STORE),
            code="T1",
            name="Till 1",
            key_hash="ab" * 32,
            key_hint="till",
        )
    )
    session.commit()
    clear_settings_cache()
    live = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown", mode="fresh"))
    assert live.status_code == 200, live.text
    assert live.json()["mode"] == "fresh" and live.json()["opening_stock"] == "reset"
    session.expire_all()
    assert _count(session, Product) == 0
    assert _count(session, Device) == 0
    assert _count(session, User) == 1
    assert session.get(User, uuid.UUID(admin_id)) is not None
    assert _count(session, Store) == 1
    settings = client.get("/api/v1/settings", headers=headers).json()
    assert settings["practice_mode"] is False and settings["onboarded"] is False
    assert settings["legal_name"] == "Downtown" and settings["trn"] == "100000000000003"


def test_go_live_deletes_simulation_tax_stamps(client, session) -> None:
    seed(client)
    _practice(session)
    row = load_settings(session)
    row.trn = "311111111111113"
    row.tax_authority = "zatca"
    session.add(
        TaxAuthorityCredential(
            authority="zatca",
            environment="simulation",
            private_key_encrypted="enc",
            certificate_pem="pem",
        )
    )
    session.add(EInvoiceChain(authority="zatca", last_counter=4, last_hash="practice"))
    session.commit()
    clear_settings_cache()
    headers, _ = admin(client)
    live = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown"))
    assert live.status_code == 200, live.text
    session.expire_all()
    assert session.scalar(select(TaxAuthorityCredential).where(TaxAuthorityCredential.authority == "zatca")) is None
    assert session.scalar(select(EInvoiceChain).where(EInvoiceChain.authority == "zatca")) is None
    settings = client.get("/api/v1/settings", headers=headers).json()
    assert settings["trn"] == "311111111111113"
    assert settings["tax_portal_pending"] is True


def test_promoted_store_rejects_practice_replays_and_keeps_duplicates(client, session) -> None:
    seed(client)
    _practice(session)
    headers, _ = admin(client)
    body = sale([line(CABLE, 1, 1500)])
    first = push(client, [event("practice-sale-kept", "sale", body)])
    assert first.status_code == 200, first.text
    assert _count(session, SyncEvent, SyncEvent.idempotency_key == "practice-sale-kept") == 1
    live = client.post("/api/v1/onboarding/go-live", headers=headers, json=_go("Downtown"))
    assert live.status_code == 200, live.text
    session.expire_all()
    assert _count(session, SyncEvent, SyncEvent.idempotency_key == "practice-sale-kept") == 1
    again = push(client, [event("practice-sale-kept", "sale", body)])
    assert again.status_code == 200, again.text
    assert again.json()["results"] == [{"idempotency_key": "practice-sale-kept", "status": "duplicate"}]
    late = push(client, [event("practice-sale-late", "sale", sale([line(CABLE, 1, 1500)]))])
    assert (late.status_code, late.json()["error"]["code"]) == (422, "sync_rejected")
    assert _count(session, Sale) == 0
