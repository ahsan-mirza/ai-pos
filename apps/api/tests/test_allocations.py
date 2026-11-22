"""Per-terminal allocation. In-memory or temporary SQLite only."""

import base64
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.deps import Principal, hash_device_key
from app.core.permissions import Permission
from app.models import Base
from app.models.batch import BatchItem, PurchaseBatch
from app.models.user import User
from app.models.device import Device
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.terminal_allocation import TerminalAllocation
from app.services.allocation_service import issue_allocation
from app.services.inventory import move_stock
from tests.test_sync import event, push

RFC_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
STORE = "00000000-0000-4000-8000-0000000000b1"
PRODUCT = "00000000-0000-4000-8000-0000000000b2"
CASHIER = "00000000-0000-4000-8000-000000000002"


@pytest.fixture(autouse=True)
def signing_key() -> None:
    settings = get_settings()
    settings.entitlement_signing_seed = base64.b64encode(RFC_SEED).decode("ascii")
    settings.entitlement_signing_key_id = "o2-test"
    yield
    settings.entitlement_signing_seed = ""
    settings.entitlement_signing_key_id = ""


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": "root-password-123"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _seed(client, *, stock: int = 100, serialized: bool = False, product_id: str = PRODUCT) -> None:
    store = push(client, [event("o6-store", "store", {"id": STORE, "code": "O6", "name": "Allocation", "currency": "USD"})])
    assert store.status_code == 200, store.text
    product = push(
        client,
        [
            event(
                f"o6-product-{product_id[-4:]}",
                "product",
                {
                    "id": product_id,
                    "store_id": STORE,
                    "sku": f"O6-{product_id[-4:]}",
                    "barcode": f"2000000000{product_id[-2:]}",
                    "name": "Allocated item",
                    "category": "General",
                    "price_cents": 1000,
                    "currency": "USD",
                    "is_serialized": serialized,
                    "stock_quantity": stock,
                },
            )
        ],
    )
    assert product.status_code == 200, product.text


def _device(session: Session, code: str, token: str) -> Device:
    row = Device(
        id=uuid.uuid4(),
        store_id=uuid.UUID(STORE),
        code=code,
        name=f"Till {code}",
        key_hash=hash_device_key(token),
        key_hint=token[-6:],
        device_public_key_thumbprint=("ab" if code == "A1" else "cd") * 32,
    )
    session.add(row)
    session.commit()
    return row


def _allocate(client, headers, device_id, quantity: int, **extra) -> dict:
    response = client.post(
        "/api/v1/inventory/allocations",
        headers=headers,
        json={"store_id": STORE, "device_id": str(device_id), "product_id": PRODUCT, "quantity": quantity, **extra},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _sale(quantity: int, allocation_id: str, sequence: int, *, price: int = 1000, total: int | None = None) -> dict:
    sale_id = str(uuid.uuid4())
    total = price * quantity if total is None else total
    return {
        "id": sale_id,
        "store_id": STORE,
        "cashier_id": CASHIER,
        "currency": "USD",
        "payment_method": "cash",
        "subtotal_cents": total,
        "tax_cents": 0,
        "total_cents": total,
        "client_sale_id": sale_id,
        "items": [
            {
                "id": str(uuid.uuid4()),
                "product_id": PRODUCT,
                "quantity": quantity,
                "unit_price_cents": price,
                "tax_cents": 0,
                "line_total_cents": total,
            }
        ],
        "allocations": [
            {"allocation_id": allocation_id, "sequence": sequence, "product_id": PRODUCT, "quantity": quantity}
        ],
    }


def _push_sale(client, token: str, payload: dict, key: str):
    return client.post(
        "/api/v1/sync/push",
        headers={"X-Terminal-Token": token},
        json={"device_id": "till", "events": [event(key, "sale", payload)]},
    )


def test_allocations_cannot_exceed_or_overlap_branch_stock(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    till_c = _device(session, "C1", "aipos_o6_till_c_token_value")
    assert _allocate(client, admin, till_a.id, 40)["remaining"] == 40
    assert _allocate(client, admin, till_b.id, 35)["remaining"] == 35
    assert _allocate(client, admin, till_c.id, 25)["remaining"] == 25
    refused = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={"store_id": STORE, "device_id": str(till_a.id), "product_id": PRODUCT, "quantity": 1},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "allocation_exceeds_stock"
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level is not None
    assert level.quantity_on_hand == 100
    assert level.quantity_reserved == 100
    assert session.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.product_id == uuid.UUID(PRODUCT))) == 1


def test_two_terminals_leave_twenty_five_unallocated(client, session: Session) -> None:
    """Branch stock 100. Terminals receive 40 and 35. The other 25 stays unallocated."""
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o83_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o83_till_b_token_value")
    assert _allocate(client, admin, till_a.id, 40)["remaining"] == 40
    assert _allocate(client, admin, till_b.id, 35)["remaining"] == 35
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level is not None
    assert level.quantity_on_hand == 100
    assert level.quantity_reserved == 75
    assert level.quantity_on_hand - level.quantity_reserved == 25
    assert session.scalar(select(func.count()).select_from(TerminalAllocation)) == 2
    later = _allocate(client, admin, till_a.id, 25)
    assert later["remaining"] == 25
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_reserved == 100
    refused = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={"store_id": STORE, "device_id": str(till_b.id), "product_id": PRODUCT, "quantity": 1},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "allocation_exceeds_stock"


def test_offline_sales_consume_only_their_own_allocation(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    grant_a = _allocate(client, admin, till_a.id, 40)
    grant_b = _allocate(client, admin, till_b.id, 35)
    sale_a = _sale(30, grant_a["id"], 1)
    first = _push_sale(client, "aipos_o6_till_a_token_value", sale_a, "o6-sale-a")
    assert first.status_code == 200, first.text
    assert first.json()["results"][0]["status"] == "applied"
    stolen = _push_sale(client, "aipos_o6_till_b_token_value", _sale(1, grant_a["id"], 2), "o6-sale-stolen")
    assert stolen.status_code == 422
    sale_b = _sale(25, grant_b["id"], 1)
    second = _push_sale(client, "aipos_o6_till_b_token_value", sale_b, "o6-sale-b")
    assert second.status_code == 200, second.text
    replay = _push_sale(client, "aipos_o6_till_a_token_value", sale_a, "o6-sale-a")
    assert replay.status_code == 200
    assert replay.json()["results"][0]["status"] == "duplicate"
    changed = dict(sale_a)
    changed["total_cents"] = sale_a["total_cents"] + 1
    collision = _push_sale(client, "aipos_o6_till_a_token_value", changed, "o6-sale-a")
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "idempotency_conflict"
    session.expire_all()
    row_a = session.get(TerminalAllocation, uuid.UUID(grant_a["id"]))
    row_b = session.get(TerminalAllocation, uuid.UUID(grant_b["id"]))
    assert row_a.quantity_consumed == 30
    assert row_b.quantity_consumed == 25
    movements = session.scalars(select(StockMovement).where(StockMovement.movement_type == "SALE_OUT")).all()
    assert len(movements) == 2
    assert sum(item.quantity for item in movements) == -55
    over = _push_sale(client, "aipos_o6_till_a_token_value", _sale(11, grant_a["id"], 2), "o6-sale-over")
    assert over.status_code == 422
    session.expire_all()
    assert session.get(TerminalAllocation, uuid.UUID(grant_a["id"])).quantity_consumed == 30


def test_a_failed_batch_does_not_consume_allocation(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    grant = _allocate(client, admin, till_a.id, 40)
    bad = _sale(1, grant["id"], 9)
    response = client.post(
        "/api/v1/sync/push",
        headers={"X-Terminal-Token": "aipos_o6_till_a_token_value"},
        json={
            "device_id": "till",
            "events": [event("o6-batch-ok", "sale", _sale(1, grant["id"], 1)), event("o6-batch-bad", "sale", bad)],
        },
    )
    assert response.status_code == 422
    session.expire_all()
    row = session.get(TerminalAllocation, uuid.UUID(grant["id"]))
    assert row.quantity_consumed == 0
    assert row.last_sequence == 0
    assert session.scalar(select(func.count()).select_from(StockMovement).where(StockMovement.movement_type == "SALE_OUT")) == 0


def test_online_sale_and_adjustment_leave_reserved_units(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    _allocate(client, admin, till_a.id, 80)
    large = _sale(21, "00000000-0000-4000-8000-00000000c001", 1)
    large["allocations"] = []
    refused = push(client, [event("o6-online-21", "sale", large)])
    assert refused.status_code == 422
    small = _sale(20, "00000000-0000-4000-8000-00000000c002", 1)
    small["allocations"] = []
    accepted = push(client, [event("o6-online-20", "sale", small)])
    assert accepted.status_code == 200, accepted.text
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_on_hand == 80
    assert level.quantity_reserved == 80
    from app.core.errors import SyncRejected

    with pytest.raises(SyncRejected):
        move_stock(
            session,
            product_id=uuid.UUID(PRODUCT),
            store_id=uuid.UUID(STORE),
            quantity=-1,
            movement_type="AUDIT_ADJUSTMENT",
            reference_type="adjustment",
        )


def test_online_sale_spends_unreserved_stock_and_leaves_both_grants(client, session: Session) -> None:
    """Contract A: an online sale with no allocation payload sells only unreserved units.

    It does not consume terminal A or terminal B. A later offline sale still draws A's grant once.
    """
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    grant_a = _allocate(client, admin, till_a.id, 40)
    grant_b = _allocate(client, admin, till_b.id, 35)
    too_much = _sale(26, grant_a["id"], 1)
    too_much["allocations"] = []
    refused = push(client, [event("o83-online-over", "sale", too_much)])
    assert refused.status_code == 422
    online = _sale(25, grant_a["id"], 1)
    online["allocations"] = []
    accepted = push(client, [event("o83-online-25", "sale", online)])
    assert accepted.status_code == 200, accepted.text
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_on_hand == 75
    assert level.quantity_reserved == 75
    assert level.available == 0
    assert session.get(TerminalAllocation, uuid.UUID(grant_a["id"])).quantity_consumed == 0
    assert session.get(TerminalAllocation, uuid.UUID(grant_b["id"])).quantity_consumed == 0
    offline = _sale(10, grant_a["id"], 1)
    first = _push_sale(client, "aipos_o6_till_a_token_value", offline, "o83-offline-a")
    assert first.status_code == 200, first.text
    stolen = _push_sale(client, "aipos_o6_till_a_token_value", _sale(1, grant_b["id"], 1), "o83-steal-b")
    assert stolen.status_code == 422
    replay = _push_sale(client, "aipos_o6_till_a_token_value", offline, "o83-offline-a")
    assert replay.status_code == 200
    assert replay.json()["results"][0]["status"] == "duplicate"
    changed = dict(offline)
    changed["total_cents"] = offline["total_cents"] + 1
    collision = _push_sale(client, "aipos_o6_till_a_token_value", changed, "o83-offline-a")
    assert collision.status_code == 409
    assert collision.json()["error"]["code"] == "idempotency_conflict"
    session.expire_all()
    assert session.get(TerminalAllocation, uuid.UUID(grant_a["id"])).quantity_consumed == 10
    assert session.get(TerminalAllocation, uuid.UUID(grant_b["id"])).quantity_consumed == 0
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_on_hand == 65
    assert level.quantity_reserved == 65
    assert level.available == 0
    movements = session.scalars(select(StockMovement).where(StockMovement.movement_type == "SALE_OUT")).all()
    assert len(movements) == 2
    assert sum(item.quantity for item in movements) == -35


def test_two_terminals_keep_40_and_35_and_online_uses_the_unallocated_25(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    grant_a = _allocate(client, admin, till_a.id, 40)
    grant_b = _allocate(client, admin, till_b.id, 35)
    over_a = _push_sale(client, "aipos_o6_till_a_token_value", _sale(41, grant_a["id"], 1), "o84-a-41")
    assert over_a.status_code == 422
    stolen = _push_sale(client, "aipos_o6_till_a_token_value", _sale(1, grant_b["id"], 1), "o84-steal")
    assert stolen.status_code == 422
    online_over = _sale(26, grant_a["id"], 1)
    online_over["allocations"] = []
    assert push(client, [event("o84-online-26", "sale", online_over)]).status_code == 422
    online = _sale(25, grant_a["id"], 1)
    online["allocations"] = []
    assert push(client, [event("o84-online-25", "sale", online)]).status_code == 200
    sale_a = _sale(40, grant_a["id"], 1)
    assert _push_sale(client, "aipos_o6_till_a_token_value", sale_a, "o84-a-40").status_code == 200
    sale_b = _sale(35, grant_b["id"], 1)
    assert _push_sale(client, "aipos_o6_till_b_token_value", sale_b, "o84-b-35").status_code == 200
    replay = _push_sale(client, "aipos_o6_till_a_token_value", sale_a, "o84-a-40")
    assert replay.status_code == 200
    assert replay.json()["results"][0]["status"] == "duplicate"
    changed = dict(sale_b)
    changed["total_cents"] = sale_b["total_cents"] + 1
    collision = _push_sale(client, "aipos_o6_till_b_token_value", changed, "o84-b-35")
    assert collision.status_code == 409
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_on_hand == 0
    assert level.quantity_reserved == 0
    assert level.available == 0
    assert session.get(TerminalAllocation, uuid.UUID(grant_a["id"])).quantity_consumed == 40
    assert session.get(TerminalAllocation, uuid.UUID(grant_b["id"])).quantity_consumed == 35
    movements = session.scalars(select(StockMovement).where(StockMovement.movement_type == "SALE_OUT")).all()
    assert len(movements) == 3
    assert sum(item.quantity for item in movements) == -100


def test_release_requires_the_synced_balance_and_a_return_does_not_refill_it(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    grant = _allocate(client, admin, till_a.id, 40)
    sale = _sale(30, grant["id"], 1)
    assert _push_sale(client, "aipos_o6_till_a_token_value", sale, "o6-release-sale").status_code == 200
    move_stock(
        session,
        product_id=uuid.UUID(PRODUCT),
        store_id=uuid.UUID(STORE),
        quantity=5,
        movement_type="RETURN_IN",
        reference_type="sale_return",
    )
    session.commit()
    session.expire_all()
    assert session.get(TerminalAllocation, uuid.UUID(grant["id"])).remaining == 10
    mismatch = client.post(
        f"/api/v1/inventory/allocations/{grant['id']}/release",
        headers=admin,
        json={"confirmed_sequence": 0, "confirmed_remaining": 40},
    )
    assert mismatch.status_code == 409
    released = client.post(
        f"/api/v1/inventory/allocations/{grant['id']}/release",
        headers=admin,
        json={"confirmed_sequence": 1, "confirmed_remaining": 10},
    )
    assert released.status_code == 200, released.text
    assert released.json()["status"] == "RELEASED"
    again = _push_sale(client, "aipos_o6_till_a_token_value", _sale(1, grant["id"], 2), "o6-after-release")
    assert again.status_code == 422
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_reserved == 0


def test_a_disconnected_terminal_keeps_its_reservation(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    grant = _allocate(client, admin, till_a.id, 40)
    held = client.post(f"/api/v1/inventory/allocations/{grant['id']}/quarantine", headers=admin)
    assert held.status_code == 200
    refused = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={"store_id": STORE, "device_id": str(till_b.id), "product_id": PRODUCT, "quantity": 61},
    )
    assert refused.status_code == 409
    session.expire_all()
    level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(PRODUCT)))
    assert level.quantity_reserved == 40
    assert session.get(TerminalAllocation, uuid.UUID(grant["id"])).status == "QUARANTINED"


def test_a_cashier_cannot_allocate(client, session: Session) -> None:
    _seed(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    signed = client.post(
        "/api/v1/auth/login-pin",
        json={"username": "cashier", "pin": "1357"},
        headers={"X-Api-Key": "test-api-key-value"},
    )
    assert signed.status_code == 200, signed.text
    response = client.post(
        "/api/v1/inventory/allocations",
        headers={"Authorization": f"Bearer {signed.json()['access_token']}"},
        json={"store_id": STORE, "device_id": str(till_a.id), "product_id": PRODUCT, "quantity": 1},
    )
    assert response.status_code == 403


def test_weighed_and_serial_allocations_stay_exact(client, session: Session) -> None:
    _seed(client, stock=25_500)
    product = session.get(Product, uuid.UUID(PRODUCT))
    product.sold_by_weight = True
    session.commit()
    admin = _admin(client)
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    grant = _allocate(client, admin, till_a.id, 25_500)
    assert grant["unit"] == "g"
    assert _push_sale(client, "aipos_o6_till_a_token_value", _sale(4_250, grant["id"], 1, total=4_250), "o6-grams").status_code == 200
    over = _push_sale(client, "aipos_o6_till_a_token_value", _sale(21_251, grant["id"], 2, total=21_251), "o6-grams-over")
    assert over.status_code == 422
    session.expire_all()
    assert session.get(TerminalAllocation, uuid.UUID(grant["id"])).remaining == 21_250

    phone = "00000000-0000-4000-8000-0000000000b3"
    _seed(client, stock=2, serialized=True, product_id=phone)
    serial = SerialNumber(
        product_id=uuid.UUID(phone),
        store_id=uuid.UUID(STORE),
        kind="imei",
        value_hash="a" * 64,
        value_encrypted="cipher",
        status="in_stock",
    )
    session.add(serial)
    phone_level = session.scalar(select(InventoryLevel).where(InventoryLevel.product_id == uuid.UUID(phone)))
    if phone_level is None:
        phone_level = InventoryLevel(product_id=uuid.UUID(phone), store_id=uuid.UUID(STORE), quantity_on_hand=2, quantity_reserved=0)
        session.add(phone_level)
    else:
        phone_level.quantity_on_hand = 2
        phone_level.quantity_reserved = 0
    session.commit()
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    first = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={
            "store_id": STORE,
            "device_id": str(till_a.id),
            "product_id": phone,
            "quantity": 1,
            "serial_number_id": str(serial.id),
        },
    )
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={
            "store_id": STORE,
            "device_id": str(till_b.id),
            "product_id": phone,
            "quantity": 1,
            "serial_number_id": str(serial.id),
        },
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "serial_allocated"


def test_the_same_lot_cannot_be_allocated_twice(client, session: Session) -> None:
    _seed(client, stock=10)
    admin = _admin(client)
    actor = session.scalar(select(User).where(User.username == "admin"))
    batch = PurchaseBatch(
        batch_number="O6-LOT",
        store_id=uuid.UUID(STORE),
        import_source="MANUAL",
        total_cost_amount=0,
        total_items_count=4,
        currency="USD",
        status="ACTIVE",
        created_by_id=actor.id,
    )
    session.add(batch)
    session.flush()
    lot = BatchItem(
        batch_id=batch.id,
        product_id=uuid.UUID(PRODUCT),
        store_id=uuid.UUID(STORE),
        quantity_imported=4,
        quantity_remaining=4,
        purchase_cost_per_unit=100,
        selling_price_per_unit=1000,
        lot_status="RELEASED",
    )
    session.add(lot)
    session.commit()
    till_a = _device(session, "A1", "aipos_o6_till_a_token_value")
    till_b = _device(session, "B1", "aipos_o6_till_b_token_value")
    assert _allocate(client, admin, till_a.id, 3, batch_item_id=str(lot.id))["remaining"] == 3
    overlap = client.post(
        "/api/v1/inventory/allocations",
        headers=admin,
        json={
            "store_id": STORE,
            "device_id": str(till_b.id),
            "product_id": PRODUCT,
            "quantity": 2,
            "batch_item_id": str(lot.id),
        },
    )
    assert overlap.status_code == 409
    assert overlap.json()["error"]["code"] == "lot_overlap"


def test_two_writers_cannot_reserve_the_same_units(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'o6-allocation.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(engine)
    setup = Session(engine)
    store_id = uuid.uuid4()
    product_id = uuid.uuid4()
    setup.add(Store(id=store_id, code="O6", name="Allocation", currency="USD"))
    setup.add(Product(id=product_id, sku="O6", barcode="O6", name="Item", category="General", price_cents=100, currency="USD"))
    setup.flush()
    devices = []
    for code in ("A1", "B1"):
        row = Device(
            store_id=store_id,
            code=code,
            name=code,
            key_hash=hash_device_key(f"aipos_o6_{code}"),
            key_hint=code,
            device_public_key_thumbprint="ab" * 32,
        )
        setup.add(row)
        devices.append(row)
    setup.flush()
    setup.add(InventoryLevel(product_id=product_id, store_id=store_id, quantity_on_hand=100, quantity_reserved=0))
    setup.commit()
    device_ids = [row.id for row in devices]
    setup.close()
    errors: list[str] = []
    lock = threading.Lock()

    def worker(device_id: uuid.UUID) -> None:
        db = Session(engine)
        try:
            issue_allocation(
                db,
                Principal(
                    kind="user",
                    scope="portal",
                    permissions=frozenset({Permission.INVENTORY_ADJUST_STOCK.value}),
                ),
                store_id=store_id,
                device_id=device_id,
                product_id=product_id,
                quantity=60,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            with lock:
                errors.append(type(exc).__name__)
        finally:
            db.close()

    threads = [threading.Thread(target=worker, args=(device_id,)) for device_id in device_ids]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    check = Session(engine)
    try:
        reserved = check.scalar(select(InventoryLevel.quantity_reserved).where(InventoryLevel.product_id == product_id))
        active = check.scalar(
            select(func.coalesce(func.sum(TerminalAllocation.quantity_allocated), 0)).where(
                TerminalAllocation.product_id == product_id,
                TerminalAllocation.status == "ACTIVE",
            )
        )
    finally:
        check.close()
        engine.dispose()
    assert reserved == 60
    assert active == 60
    assert len(errors) == 1


def test_allocation_feed_returns_only_this_register(client, session: Session) -> None:
    _seed(client)
    admin = _admin(client)
    first = _device(session, "A1", "aipos_o85_till_a_token_value")
    second = _device(session, "B1", "aipos_o85_till_b_token_value")
    _allocate(client, admin, first.id, 40)
    _allocate(client, admin, second.id, 35)
    own = client.get(
        "/api/v1/inventory/allocation-feed",
        headers={"X-Terminal-Token": "aipos_o85_till_a_token_value"},
    )
    assert own.status_code == 200, own.text
    rows = own.json()["allocations"]
    assert len(rows) == 1
    assert rows[0]["device_id"] == str(first.id)
    assert rows[0]["payload"] and rows[0]["signature"] and rows[0]["key_id"]
    other = client.get(
        "/api/v1/inventory/allocation-feed",
        headers={"X-Terminal-Token": "aipos_o85_till_b_token_value"},
    )
    assert other.status_code == 200, other.text
    assert [row["device_id"] for row in other.json()["allocations"]] == [str(second.id)]
    refused = client.get("/api/v1/inventory/allocation-feed")
    assert refused.status_code == 401
