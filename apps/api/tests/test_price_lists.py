import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models.audit_log import AuditLog
from app.models.price_list import ScheduledPriceChange
from app.models.sale_item import SaleItem
from app.services import price_list_service
from test_foundations import set_tax
from wholesale_support import CABLE, STORE, admin, create_customer, device, event, line, push, sale, seed


def group(client, headers, **body) -> dict:
    response = client.post("/api/v1/price-lists/groups", headers=headers, json={"name": "Dealers", **body})
    assert response.status_code == 201, response.text
    return response.json()


def price_list(client, headers, items: list[dict], **body) -> dict:
    created = client.post("/api/v1/price-lists", headers=headers, json={"name": "List", "scope": "global", **body})
    assert created.status_code == 201, created.text
    filled = client.put(f"/api/v1/price-lists/{created.json()['id']}/items", headers=headers, json={"items": items})
    assert filled.status_code == 200, filled.text
    return filled.json()


def mismatches(session) -> list[AuditLog]:
    return list(session.scalars(select(AuditLog).where(AuditLog.action == "sale.price_list_mismatch")))


def sold_line(session, sale_id: str) -> SaleItem:
    return session.scalar(select(SaleItem).where(SaleItem.sale_id == uuid.UUID(sale_id)))


def test_group_and_customer_lists_price_wholesale_sales(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    dealers = group(client, headers, default_discount_bps=500)
    customer = create_customer(client, headers, group_id=dealers["id"], price_tier="RETAIL", credit_limit_cents=0)
    dealer_list = price_list(
        client, headers, [{"product_id": CABLE, "price_cents": 1250}], scope="group", scope_id=dealers["id"]
    )

    body = sale([line(CABLE, 2, 1250)], sale_type="WHOLESALE", customer_id=customer["id"])
    assert push(client, [event("group-price", "sale", body)]).status_code == 200
    item = sold_line(session, body["id"])
    assert (item.price_source, item.price_list_id) == ("group_list", uuid.UUID(dealer_list["id"]))
    assert mismatches(session) == []

    # A register still on the blanket 5% discount (1425) is not wrong: that price is valid too.
    stale = sale([line(CABLE, 1, 1425)], sale_type="WHOLESALE", customer_id=customer["id"])
    assert push(client, [event("group-discount", "sale", stale)]).status_code == 200
    assert mismatches(session) == []

    own = price_list(
        client, headers, [{"product_id": CABLE, "price_cents": 1200}], scope="customer", scope_id=customer["id"]
    )
    cached = client.get(f"/api/v1/price-lists/customers/{customer['id']}", headers=device()).json()
    assert {entry["price_list_id"] for entry in cached["entries"]} >= {own["id"]}
    assert any(entry["product_id"] is None and entry["discount_bps"] == 500 for entry in cached["entries"])

    wrong = sale([line(CABLE, 1, 1100)], sale_type="WHOLESALE", customer_id=customer["id"])
    assert push(client, [event("no-such-price", "sale", wrong)]).status_code == 200
    [audit] = mismatches(session)
    assert audit.details["lines"][0]["server_cents"] == 1200


def test_store_lists_reach_that_branch_only_and_expire(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    uptown = str(uuid.uuid4())
    store = {"id": uptown, "code": "UP-02", "name": "Uptown", "currency": "USD"}
    assert push(client, [event("uptown-store", "store", store)]).status_code == 200
    branch = price_list(client, headers, [{"product_id": CABLE, "price_cents": 1300}], scope="store", scope_id=STORE)
    here = client.get(f"/api/v1/products/{CABLE}", headers=device(), params={"store_id": STORE}).json()
    assert [entry["price_list_id"] for entry in here["price_lists"]] == [branch["id"]]
    there = client.get(f"/api/v1/products/{CABLE}", headers=device(), params={"store_id": uptown}).json()
    assert there["price_lists"] == []

    body = sale([line(CABLE, 1, 1300)])
    assert push(client, [event("store-price", "sale", body)]).status_code == 200
    assert sold_line(session, body["id"]).price_source == "store_list"

    past = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    ended = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    updated = client.put(
        f"/api/v1/price-lists/{branch['id']}",
        headers=headers,
        json={"name": "Old offer", "scope": "store", "scope_id": STORE, "valid_from": past, "valid_to": ended},
    )
    assert updated.status_code == 200 and updated.json()["status"] == "expired"
    late = sale([line(CABLE, 1, 1300)])
    assert push(client, [event("expired-price", "sale", late)]).status_code == 200
    assert len(mismatches(session)) == 1


def test_scheduled_change_applies_audits_and_prints_labels(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    future = client.post(
        "/api/v1/price-lists/changes",
        headers=headers,
        json={
            "name": "Autumn prices",
            "run_at": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
            "lines": [{"product_id": CABLE, "retail_price_cents": 1700, "tier_prices": {"TIER_1": 1400}}],
        },
    )
    assert future.status_code == 201, future.text
    assert price_list_service.apply_due(session) == "0 price changes applied"

    change = future.json()
    row = session.get(ScheduledPriceChange, uuid.UUID(change["id"]))
    row.run_at = datetime.now(UTC) - timedelta(minutes=1)
    session.commit()
    assert price_list_service.apply_due(session) == "1 price changes applied"

    product = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert product["price_cents"] == 1700
    assert {row["price_tier"]: row["price_cents"] for row in product["prices"]}["TIER_1"] == 1400
    detail = client.get(f"/api/v1/price-lists/changes/{change['id']}", headers=headers).json()
    assert detail["status"] == "APPLIED" and detail["lines"][0]["previous_retail_cents"] == 1500
    assert session.scalar(select(AuditLog).where(AuditLog.action == "price_change.apply")) is not None
    labels = client.get(f"/api/v1/price-lists/changes/{change['id']}/labels.pdf", headers=headers)
    assert labels.status_code == 200 and labels.content.startswith(b"%PDF")
    assert client.post(f"/api/v1/price-lists/changes/{change['id']}/cancel", headers=headers).status_code == 409


def test_zero_rated_export_customer(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    exporter = create_customer(
        client, headers, tax_treatment="ZERO_EXPORT", tax_certificate_ref="EXP-77", credit_limit_cents=0
    )
    zero = sale([line(CABLE, 2, 1500)], customer_id=exporter["id"], sold_at=datetime.now(UTC).isoformat())
    assert push(client, [event("export-sale", "sale", zero)]).status_code == 200, "zero-rated line accepted"
    assert sold_line(session, zero["id"]).tax_treatment == "ZERO_EXPORT"

    # A register that never learned the customer's treatment charged 5%: the sale stays as charged.
    taxed = sale([line(CABLE, 1, 1500)], customer_id=exporter["id"], sold_at=datetime.now(UTC).isoformat())
    taxed["items"][0].update(tax_cents=75, line_total_cents=1575)
    taxed.update(tax_cents=75, total_cents=1575)
    assert push(client, [event("export-standard", "sale", taxed)]).status_code == 200
    assert sold_line(session, taxed["id"]).tax_treatment is None

    today = datetime.now(UTC).date()
    report = client.get("/api/v1/reports/vat", headers=headers, params={"from": str(today), "to": str(today)}).json()
    zero_box = next(box for box in report["boxes"] if box["key"] == "4")
    assert zero_box["amount_cents"] == 3000

    expired = client.patch(
        f"/api/v1/customers/{exporter['id']}",
        headers=headers,
        json={"tax_certificate_expiry": str(date.today() - timedelta(days=1))},
    )
    assert expired.status_code == 200 and expired.json()["tax_certificate_expiry"]
    lapsed = sale([line(CABLE, 1, 1500)], customer_id=exporter["id"], sold_at=datetime.now(UTC).isoformat())
    response = push(client, [event("export-lapsed", "sale", lapsed)])
    assert response.status_code == 422 and "VAT" in response.json()["error"]["message"]


def test_price_list_csv_round_trip(client) -> None:
    seed(client)
    headers, _ = admin(client)
    created = price_list(client, headers, [])
    csv = "sku,price,discount_percent,min_qty\nACC-CABLE-USBC,12.50,,10\nPHN-PIXEL-9,,7.5,\nNOPE,1,,\n"
    imported = client.post(f"/api/v1/price-lists/{created['id']}/import", headers=headers, json={"csv": csv})
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 2 and "NOPE" in imported.json()["skipped"][0]
    detail = client.get(f"/api/v1/price-lists/{created['id']}", headers=headers).json()
    by_sku = {row["sku"]: row for row in detail["lines"]}
    assert (by_sku["ACC-CABLE-USBC"]["price_cents"], by_sku["ACC-CABLE-USBC"]["min_qty"]) == (1250, 10)
    assert by_sku["PHN-PIXEL-9"]["discount_bps"] == 750
    exported = client.get(f"/api/v1/price-lists/{created['id']}/export.csv", headers=headers)
    assert exported.status_code == 200 and "ACC-CABLE-USBC" in exported.text and "12.50" in exported.text
    assert client.delete(f"/api/v1/price-lists/{created['id']}", headers=headers).status_code == 204
