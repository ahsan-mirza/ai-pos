import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import cable_batch, import_storage, on_hand  # noqa: F401
from tests.test_returns import CABLE_ID, STORE_ID, admin_token, bearer, record_sale, seed_catalog

from app.core import capabilities as catalog
from app.models import AuditLog, BatchAllocation, BatchItem, SaleItem
from app.services.batch_ledger import today


def enable_fefo(client, token: str) -> None:
    modules = [capability.value for capability in catalog.ELECTRONICS_WHOLESALE] + ["fefo"]
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": "electronics_wholesale", "capabilities": modules},
    )
    assert response.status_code == 200, response.text
    assert "fefo" in response.json()["capabilities"]


def set_expiry(session: Session, batch: dict, days: int | None) -> uuid.UUID:
    item = session.get(BatchItem, uuid.UUID(batch["items"][0]["id"]))
    item.expiry_date = None if days is None else today() + timedelta(days=days)
    session.commit()
    return item.id


def drawn(session: Session, sale: dict) -> dict[uuid.UUID, int]:
    session.expire_all()
    item = session.get(SaleItem, uuid.UUID(sale["items"][0]["id"]))
    rows = session.scalars(select(BatchAllocation).where(BatchAllocation.sale_item_id == item.id)).all()
    return {row.batch_item_id: row.quantity for row in rows}


def test_fifo_stays_the_default_without_the_module(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    older = set_expiry(session, cable_batch(client, token, 3, "5.00"), 90)
    set_expiry(session, cable_batch(client, token, 3, "6.00"), 5)
    sale = record_sale(client, product_id=CABLE_ID, price=1500, quantity=2)
    assert drawn(session, sale) == {older: 2}


def test_fefo_sells_soonest_expiry_first_and_expired_last(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable_fefo(client, token)
    expired = set_expiry(session, cable_batch(client, token, 2, "4.00"), -3)
    later = set_expiry(session, cable_batch(client, token, 2, "5.00"), 60)
    sooner = set_expiry(session, cable_batch(client, token, 2, "6.00"), 10)
    undated = set_expiry(session, cable_batch(client, token, 2, "7.00"), None)

    first = record_sale(client, product_id=CABLE_ID, price=1500, quantity=3)
    assert drawn(session, first) == {sooner: 2, later: 1}
    assert session.scalar(select(AuditLog).where(AuditLog.action == "inventory.expired_sold")) is None

    second = record_sale(client, product_id=CABLE_ID, price=1500, quantity=4)
    assert drawn(session, second) == {later: 1, undated: 2, expired: 1}
    flagged = session.scalars(select(BatchAllocation).where(BatchAllocation.batch_item_id == expired)).all()
    assert [row.expired for row in flagged] == [True]
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "inventory.expired_sold"))
    assert entry is not None and entry.action_type == "EXPIRED_STOCK_SOLD"
    assert entry.details["quantity"] == 1


def test_expiring_report_write_off_and_settings(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert client.get("/api/v1/inventory/expiring", headers=bearer(token)).status_code == 403
    enable_fefo(client, token)
    expired = set_expiry(session, cable_batch(client, token, 4, "5.00"), -1)
    soon = set_expiry(session, cable_batch(client, token, 2, "5.00"), 10)
    set_expiry(session, cable_batch(client, token, 2, "5.00"), 200)

    rows = client.get("/api/v1/inventory/expiring", headers=bearer(token)).json()
    assert [(row["batch_item_id"], row["expired"]) for row in rows] == [(str(expired), True), (str(soon), False)]
    assert rows[0]["days_left"] == -1 and rows[0]["value_cents"] == 2000
    assert len(client.get("/api/v1/inventory/expiring?days=365", headers=bearer(token)).json()) == 3

    fresh = client.post("/api/v1/inventory/expiry-writeoff", headers=bearer(token), json={"batch_item_id": str(soon)})
    assert fresh.status_code == 422 and fresh.json()["error"]["code"] == "not_expired"
    before = on_hand(session, CABLE_ID)
    done = client.post("/api/v1/inventory/expiry-writeoff", headers=bearer(token), json={"batch_item_id": str(expired)})
    assert done.status_code == 200, done.text
    assert done.json()["written_off"] == 4 and done.json()["quantity_remaining"] == 0
    assert on_hand(session, CABLE_ID) == before - 4

    settings = client.get("/api/v1/settings", headers=bearer(token)).json()["module_settings"]
    assert settings["fefo"]["alert_days"] == 14
    settings["fefo"]["alert_days"] = 300
    saved = client.put("/api/v1/settings/modules", headers=bearer(token), json=settings)
    assert saved.status_code == 200, saved.text
    widened = client.get("/api/v1/inventory/expiring", headers=bearer(token)).json()
    assert len(widened) == 2
    assert {row["store_id"] for row in widened} == {STORE_ID}
