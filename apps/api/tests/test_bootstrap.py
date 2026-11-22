"""Catalogue bootstrap. Uses the in-memory SQLite suite, not a protected database."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base
from app.models.bootstrap import BootstrapSession
from app.models.device import Device
from app.models.product import Product
from app.services.bootstrap_service import allocate_seqs, note_retention
from tests.test_inventory import DT, admin, seed
from tests.test_terminal_activation import _key


def _token(client, headers, code: str) -> tuple[str, str]:
    created = client.post("/api/v1/devices", headers=headers, json={"store_id": DT, "code": code, "name": code})
    assert created.status_code == 201, created.text
    device_id = created.json()["device"]["id"]
    activated = client.post(
        "/api/v1/terminals/activate",
        json={"activation_key": _key(client, headers, device_id), "machine_name": code},
    )
    assert activated.status_code == 200, activated.text
    return device_id, activated.json()["device_token"]


def test_snapshot_pages_stay_frozen_and_pull_is_scoped(client, session: Session) -> None:
    seed(client)
    headers = admin(client)
    device_id, token = _token(client, headers, "B1")
    auth = {"X-Terminal-Token": token}
    started = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["branch_id"]
    assert body["terminal_id"] == device_id
    seen: list[str] = []
    after = -1
    pages = 0
    first_page = None
    while True:
        response = client.get(
            f"/api/v1/terminals/bootstrap/sessions/{body['session_id']}/pages",
            headers=auth,
            params={"dataset": "products", "after_position": after, "limit": 1},
        )
        assert response.status_code == 200, response.text
        page = response.json()
        pages += 1
        if first_page is None:
            first_page = page
        for record in page["records"]:
            seen.append(record["id"])
            assert record["record"]["stock_authoritative"] is True
        if page["done"]:
            break
        after = page["next_position"]
        assert pages <= body["product_count"] + 1
    if body["product_count"]:
        assert pages == body["product_count"]
        assert len(seen) == len(set(seen)) == body["product_count"]
    assert first_page is not None
    repeated = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{body['session_id']}/pages",
        headers=auth,
        params={"dataset": "products", "after_position": -1, "limit": 1},
    )
    assert repeated.json()["records"] == first_page["records"]
    denied = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{body['session_id']}/pages",
        headers=auth,
        params={"dataset": "customers", "after_position": -1, "limit": 1},
    )
    assert denied.status_code == 403
    assert "customers" not in denied.text

    session.expire_all()
    product = session.scalar(select(Product).limit(1))
    assert product is not None
    original = product.name
    product.name = f"{original} edited"
    session.commit()
    repeated_after = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{body['session_id']}/pages",
        headers=auth,
        params={"dataset": "products", "after_position": -1, "limit": 1},
    )
    assert repeated_after.json()["records"] == first_page["records"]
    pulled = client.get(
        "/api/v1/terminals/bootstrap/pull",
        headers=auth,
        params={"cursor": first_page["cursor"], "limit": 50},
    )
    assert pulled.status_code == 200, pulled.text
    assert any(change["record_id"] == str(product.id) and change["operation"] == "upsert" for change in pulled.json()["changes"])
    assert all(change["record"]["stock_authoritative"] is False for change in pulled.json()["changes"] if change["record"])

    _other_id, other_token = _token(client, headers, "B2")
    foreign = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{body['session_id']}/pages",
        headers={"X-Terminal-Token": other_token},
        params={"dataset": "products", "after_position": -1, "limit": 1},
    )
    assert foreign.status_code == 404
    stolen = client.get(
        "/api/v1/terminals/bootstrap/pull",
        headers={"X-Terminal-Token": other_token},
        params={"cursor": first_page["cursor"], "limit": 10},
    )
    assert stolen.status_code in {401, 403}

    tampered = first_page["cursor"][:-2] + ("aa" if not first_page["cursor"].endswith("aa") else "bb")
    bad = client.get("/api/v1/terminals/bootstrap/pull", headers=auth, params={"cursor": tampered, "limit": 10})
    assert bad.status_code == 401

    again = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert again.status_code == 200, again.text
    fresh = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{again.json()['session_id']}/pages",
        headers=auth,
        params={"dataset": "products", "after_position": -1, "limit": 1},
    )
    assert fresh.status_code == 200, fresh.text
    current_cursor = fresh.json()["cursor"]
    stale = client.get(
        "/api/v1/terminals/bootstrap/pull",
        headers=auth,
        params={"cursor": first_page["cursor"], "limit": 10},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "cursor_generation"

    note_retention(session, int(again.json()["since_seq"]) + 1)
    session.commit()
    retained = client.get(
        "/api/v1/terminals/bootstrap/pull",
        headers=auth,
        params={"cursor": current_cursor, "limit": 10},
    )
    assert retained.status_code == 409
    assert retained.json()["error"]["code"] == "rebootstrap_required"

    stored = session.get(BootstrapSession, uuid.UUID(again.json()["session_id"]))
    assert stored is not None
    stored.created_at = datetime.now(UTC) - timedelta(minutes=31)
    session.commit()
    expired = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{again.json()['session_id']}/pages",
        headers=auth,
        params={"dataset": "products", "after_position": -1, "limit": 1},
    )
    assert expired.status_code == 409
    assert expired.json()["error"]["code"] == "snapshot_expired"

    device = session.get(Device, uuid.UUID(device_id))
    assert device is not None
    device.revoked_at = datetime.now(UTC)
    session.commit()
    revoked = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "device_revoked"


def test_feed_sequences_stay_unique_under_two_writers(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'o3-feed.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    assert engine.url.drivername == "sqlite"
    Base.metadata.create_all(engine)
    found: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        for _ in range(12):
            db = Session(engine)
            try:
                value = allocate_seqs(db, 1)
                db.commit()
                with lock:
                    found.append(value)
            finally:
                db.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(found) == list(range(1, 25))
    engine.dispose()


def test_an_open_snapshot_holds_the_feed_until_it_commits(tmp_path) -> None:
    """A catalogue sequence cannot commit while a snapshot still holds the counter."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'o4-snapshot-lock.sqlite'}",
        connect_args={"check_same_thread": False, "timeout": 0.2},
    )
    Base.metadata.create_all(engine)
    setup = Session(engine)
    try:
        assert allocate_seqs(setup, 0) == 0
        setup.commit()
    finally:
        setup.close()

    holder = Session(engine)
    assert allocate_seqs(holder, 0) == 0
    outcome: dict[str, object] = {}

    def challenger() -> None:
        db = Session(engine)
        try:
            outcome["seq"] = allocate_seqs(db, 1)
            db.commit()
            outcome["state"] = "committed"
        except Exception as exc:
            outcome["state"] = type(exc).__name__
            db.rollback()
        finally:
            db.close()

    thread = threading.Thread(target=challenger)
    thread.start()
    thread.join(0.8)
    assert outcome.get("state") != "committed"
    holder.commit()
    holder.close()
    thread.join(2)
    if outcome.get("state") != "committed":
        follow = Session(engine)
        try:
            outcome["seq"] = allocate_seqs(follow, 1)
            follow.commit()
            outcome["state"] = "committed"
        finally:
            follow.close()
    assert outcome["state"] == "committed"
    assert outcome["seq"] == 1
    engine.dispose()


def test_bootstrap_migration_does_not_touch_the_stock_ledger() -> None:
    text = (
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261122_0125_catalog_bootstrap.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20261122_0124"' in text
    assert "create_table" in text
    assert 'op.create_table(\n        "inventory' not in text
    assert "stock_movement" not in text


def test_one_hundred_products_use_five_pages(client) -> None:
    import time
    import uuid

    from tests.test_inventory import DT, event, push

    seed(client)
    headers = admin(client)
    _device_id, token = _token(client, headers, "B9")
    extras = [
        event(
            f"product-o3-{index}",
            "product",
            {
                "id": str(uuid.uuid4()),
                "store_id": DT,
                "sku": f"O3-{index:04d}",
                "barcode": f"31000000{index:04d}",
                "name": f"Item {index:04d}",
                "category": "General",
                "sub_category": "General",
                "price_cents": 100 + index,
                "currency": "USD",
                "is_serialized": False,
                "stock_quantity": 1,
            },
        )
        for index in range(100)
    ]
    for start in range(0, len(extras), 25):
        assert push(client, extras[start : start + 25]).status_code == 200
    auth = {"X-Terminal-Token": token}
    started = time.perf_counter()
    opened = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert opened.status_code == 200, opened.text
    session_id = opened.json()["session_id"]
    assert opened.json()["product_count"] == 102
    seen = 0
    after = -1
    pages = 0
    while True:
        page = client.get(
            f"/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
            headers=auth,
            params={"dataset": "products", "after_position": after, "limit": 25},
        )
        assert page.status_code == 200, page.text
        body = page.json()
        assert len(body["records"]) <= 25
        seen += len(body["records"])
        pages += 1
        if body["done"]:
            break
        after = body["next_position"]
    elapsed = time.perf_counter() - started
    print(f"o3 bootstrap 102 products in {pages} pages took {elapsed:.3f}s")
    assert seen == 102
    assert pages == 5
    assert elapsed < 30


def test_checkout_settings_stay_frozen_and_a_queued_rate_is_kept(client, session: Session) -> None:
    from app.core.errors import SyncRejected
    from app.models.business_settings import BusinessSettings
    from app.schemas.payloads import SaleItemPayload
    from app.services.sale_service import price_lines
    from app.services.tax import TaxPolicy, line_tax
    from app.tenancy.scoping import DEFAULT_TENANT_ID
    from tests.test_inventory import CABLE, DT

    seed(client)
    headers = admin(client)
    _device_id, token = _token(client, headers, "B8")
    rows = list(session.scalars(select(BusinessSettings).where(BusinessSettings.tenant_id == DEFAULT_TENANT_ID)))
    if not rows:
        session.add(
            BusinessSettings(
                id=uuid.uuid4(),
                tenant_id=DEFAULT_TENANT_ID,
                currency="AED",
                vat_registered=True,
                prices_include_vat=False,
                standard_rate_bps=500,
                tax_authority="fta",
            )
        )
    else:
        for existing in rows:
            existing.currency = "AED"
            existing.vat_registered = True
            existing.prices_include_vat = False
            existing.standard_rate_bps = 500
            existing.tax_authority = "fta"
    session.commit()
    auth = {"X-Terminal-Token": token}
    started = client.post("/api/v1/terminals/bootstrap/sessions", headers=auth)
    assert started.status_code == 200, started.text
    session_id = started.json()["session_id"]
    frozen = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
        headers=auth,
        params={"dataset": "checkout_settings", "after_position": -1, "limit": 1},
    )
    assert frozen.status_code == 200, frozen.text
    assert frozen.json()["records"][0]["record"]["standard_rate_bps"] == 500
    assert frozen.json()["records"][0]["record"]["currency"] == "AED"
    assert "payroll" not in frozen.json()["records"][0]["record"]
    cursor = frozen.json()["cursor"]
    session.expire_all()
    for row in session.scalars(select(BusinessSettings).where(BusinessSettings.tenant_id == DEFAULT_TENANT_ID)):
        row.standard_rate_bps = 1000
    session.commit()
    again = client.get(
        f"/api/v1/terminals/bootstrap/sessions/{session_id}/pages",
        headers=auth,
        params={"dataset": "checkout_settings", "after_position": -1, "limit": 1},
    )
    assert again.json()["records"][0]["record"]["standard_rate_bps"] == 500
    pulled = client.get("/api/v1/terminals/bootstrap/pull", headers=auth, params={"cursor": cursor, "limit": 20})
    assert pulled.status_code == 200, pulled.text
    assert any(
        change["operation"] == "settings" and change["record"]["standard_rate_bps"] == 1000
        for change in pulled.json()["changes"]
    )

    product = session.get(Product, uuid.UUID(CABLE))
    assert product is not None
    old = line_tax(1500, 1, 500, inclusive=False)
    item = SaleItemPayload(
        id=uuid.uuid4(),
        product_id=product.id,
        quantity=1,
        unit_price_cents=1500,
        tax_cents=old.tax_cents,
        line_total_cents=old.line_total_cents,
        tax_rate_bps=500,
    )
    priced = price_lines(
        session,
        items=[item],
        store_id=uuid.UUID(DT),
        currency=product.currency,
        tier="retail",
        quote=False,
        tax_policy=TaxPolicy(True, False, 1000),
    )
    assert priced.lines[0].tax_rate_bps == 500
    assert priced.tax_cents == old.tax_cents
    current = line_tax(1500, 1, 1000, inclusive=False)
    stale = item.model_copy(update={"tax_rate_bps": None})
    try:
        price_lines(
            session,
            items=[stale],
            store_id=uuid.UUID(DT),
            currency=product.currency,
            tier="retail",
            quote=False,
            tax_policy=TaxPolicy(True, False, 1000),
        )
    except SyncRejected:
        pass
    else:
        raise AssertionError("a line without a snapshotted rate must match the current tax policy")
    live = item.model_copy(update={"tax_rate_bps": None, "tax_cents": current.tax_cents, "line_total_cents": current.line_total_cents})
    accepted = price_lines(
        session,
        items=[live],
        store_id=uuid.UUID(DT),
        currency=product.currency,
        tier="retail",
        quote=False,
        tax_policy=TaxPolicy(True, False, 1000),
    )
    assert accepted.tax_cents == current.tax_cents
