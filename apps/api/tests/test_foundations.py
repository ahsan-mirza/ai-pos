import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.sale import Sale
from app.services.tax import line_tax
from wholesale_support import CABLE, STORE, admin, device, event, line, push, sale, seed

FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "fixtures" / "tax-cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_tax_matches_shared_fixture(case: dict) -> None:
    result = line_tax(case["unit"], case["quantity"], case["rate_bps"], inclusive=case["inclusive"])
    assert (result.net_cents, result.tax_cents, result.line_total_cents) == (case["net"], case["tax"], case["total"])


def set_tax(client, headers, **overrides) -> None:
    body = {
        "vat_registered": True,
        "trn": "100123456700003",
        "legal_name": "AI POS Trading LLC",
        "prices_include_vat": False,
        "standard_rate_bps": 500,
    }
    body.update(overrides)
    response = client.put("/api/v1/settings/tax", headers=headers, json=body)
    assert response.status_code == 200, response.text


def taxed_line(unit: int, quantity: int, *, inclusive: bool, rate: int = 500) -> dict:
    item = line(CABLE, quantity, unit)
    result = line_tax(unit, quantity, rate, inclusive=inclusive)
    item["tax_cents"] = result.tax_cents
    item["line_total_cents"] = result.line_total_cents
    return item


def taxed_sale(items: list[dict], **extra) -> dict:
    body = sale(items, **extra)
    body["tax_cents"] = sum(item["tax_cents"] for item in items)
    body["total_cents"] = sum(item["line_total_cents"] for item in items)
    body["subtotal_cents"] = body["total_cents"] - body["tax_cents"]
    return body


def test_register_upsert_never_reverts_portal_price(client) -> None:
    seed(client)
    headers, _ = admin(client)
    assert (
        client.put(f"/api/v1/pricing/products/{CABLE}", headers=headers, json={"retail_price_cents": 1800}).status_code
        == 200
    )
    stale = {
        "id": CABLE,
        "store_id": STORE,
        "sku": "ACC-CABLE-USBC",
        "barcode": "100000000001",
        "name": "Old cable name",
        "category": "Accessories",
        "price_cents": 1500,
        "currency": "USD",
        "is_serialized": False,
        "stock_quantity": 0,
    }
    assert push(client, [event("stale-product", "product", stale)]).status_code == 200
    product = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert (product["price_cents"], product["name"]) == (1800, "USB-C Cable")


def test_sale_is_dated_when_it_happened(client, session) -> None:
    seed(client)
    body = sale([line(CABLE, 1, 1500)])
    when = (datetime.now(UTC) - timedelta(hours=6)).replace(microsecond=0)
    offline = {**event("offline-sale", "sale", body), "occurred_at": when.isoformat()}
    assert push(client, [offline]).status_code == 200
    stored = session.get(Sale, uuid.UUID(body["id"]))
    assert stored.created_at.replace(tzinfo=UTC) == when

    ahead = datetime.now(UTC) + timedelta(hours=2)
    skewed = sale([line(CABLE, 1, 1500)], sold_at=ahead.isoformat())
    assert push(client, [event("skewed-sale", "sale", skewed)]).status_code == 200
    recorded = session.get(Sale, uuid.UUID(skewed["id"]))
    recorded_at = recorded.created_at.replace(tzinfo=UTC)
    assert recorded_at < ahead - timedelta(hours=1)
    assert abs(recorded_at - datetime.now(UTC)) < timedelta(minutes=1)

    future = sale([line(CABLE, 1, 1500)], sold_at=(datetime.now(UTC) + timedelta(days=2)).isoformat())
    rejected = push(client, [event("future-sale", "sale", future)])
    assert rejected.status_code == 422 and "future" in rejected.json()["error"]["message"]


def test_vat_is_recomputed_exclusive(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers)
    wrong = sale([line(CABLE, 2, 1500)])
    response = push(client, [event("vat-wrong", "sale", wrong)])
    assert response.status_code == 422 and "VAT" in response.json()["error"]["message"]
    good = taxed_sale([taxed_line(1500, 2, inclusive=False)])
    assert good["tax_cents"] == 150
    assert push(client, [event("vat-good", "sale", good)]).status_code == 200


def test_vat_inclusive_pricing(client) -> None:
    seed(client)
    headers, _ = admin(client)
    set_tax(client, headers, prices_include_vat=True)
    body = taxed_sale([taxed_line(1575, 4, inclusive=True)])
    assert (body["total_cents"], body["tax_cents"]) == (6300, 300)
    assert push(client, [event("vat-inclusive", "sale", body)]).status_code == 200
    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert stored["items"][0]["tax_rate_bps"] == 500
    assert stored["subtotal_cents"] == 6000


def test_tax_settings_need_trn(client) -> None:
    headers, _ = admin(client)
    response = client.put(
        "/api/v1/settings/tax",
        headers=headers,
        json={"vat_registered": True, "prices_include_vat": False, "standard_rate_bps": 500},
    )
    assert response.status_code == 422


def register_device(client, headers, code: str = "R01") -> tuple[str, dict]:
    response = client.post("/api/v1/devices", headers=headers, json={"store_id": STORE, "code": code, "name": "Till 1"})
    assert response.status_code == 201, response.text
    body = response.json()
    return body["key"], body["device"]


def test_device_keys_scope_registers_to_their_store(client) -> None:
    seed(client)
    headers, _ = admin(client)
    key, info = register_device(client, headers)
    assert info["invoice_prefix"] == "DT-01-R01"
    own = {"X-Api-Key": key}
    me = client.get("/api/v1/devices/me", headers=own).json()
    assert {item["doc_type"]: item["prefix"] for item in me["series"]}["CN"] == "DT-01-R01-CN"

    body = sale([line(CABLE, 1, 1500)], invoice_number="DT-01-R01-000001")
    pushed = client.post(
        "/api/v1/sync/push", headers=own, json={"device_id": "R01", "events": [event("dev-sale", "sale", body)]}
    )
    assert pushed.status_code == 200, pushed.text
    other_store = {"id": str(uuid.uuid4()), "code": "XX-9", "name": "Elsewhere", "currency": "USD"}
    wrong = client.post(
        "/api/v1/sync/push",
        headers=own,
        json={"device_id": "R01", "events": [event("dev-store", "store", other_store)]},
    )
    assert wrong.status_code == 422

    revoked = client.post(f"/api/v1/devices/{info['id']}/revoke", headers=headers)
    assert revoked.status_code == 200 and revoked.json()["revoked_at"] is not None
    assert client.get("/api/v1/devices/me", headers=own).status_code == 401


def test_shared_key_can_be_disabled(client, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "allow_shared_api_key", False)
    response = client.get("/api/v1/products", headers=device())
    assert response.status_code == 401


def test_register_invoice_series(client) -> None:
    seed(client)
    headers, _ = admin(client)
    key, _ = register_device(client, headers)
    own = {"X-Api-Key": key}

    def send(key_name: str, number: str | None):
        body = sale([line(CABLE, 1, 1500)], invoice_number=number) if number else sale([line(CABLE, 1, 1500)])
        return client.post(
            "/api/v1/sync/push", headers=own, json={"device_id": "R01", "events": [event(key_name, "sale", body)]}
        )

    assert send("invoice-key-1", "DT-01-R01-000001").status_code == 200
    duplicate = send("invoice-key-2", "DT-01-R01-000001")
    assert duplicate.status_code == 422 and "already used" in duplicate.json()["error"]["message"]
    foreign = send("invoice-key-3", "DT-01-R09-000002")
    assert foreign.status_code == 422 and "DT-01-R01" in foreign.json()["error"]["message"]
    assert send("invoice-key-4", None).status_code == 200
    sales = client.get("/api/v1/sales", headers=headers).json()
    assert {item["invoice_number"] for item in sales} == {"DT-01-R01-000001", "DT-01-S-000001"}
    me = client.get("/api/v1/devices/me", headers=own).json()
    assert {item["doc_type"]: item["last_value"] for item in me["series"]}["INV"] == 1
