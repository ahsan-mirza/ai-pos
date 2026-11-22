"""Laundry catalog, price quotes, and tenant-owned configuration."""

import uuid
from datetime import date, timedelta

from tests.conftest import ADMIN_PASSWORD

from app.core.capabilities import Capability
from app.models.customer import Customer
from app.models.laundry import LaundryService
from app.models.store import Store
from app.services.laundry_pricing import LaundryPriceError, net_weight, quote
from app.tenancy.scoping import DEFAULT_TENANT_ID


def _login(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _laundry(client, headers) -> None:
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={
            "business_profile": "laundry",
            "capabilities": [
                Capability.LOYALTY.value,
                Capability.PROMOTIONS.value,
                Capability.WEIGHED_ITEMS.value,
                Capability.CARD_TERMINALS.value,
                Capability.LAUNDRY_OPERATIONS.value,
            ],
        },
    )
    assert response.status_code == 200, response.text


def test_piece_and_weight_quotes_use_the_business_tax_rate() -> None:
    piece = quote(
        unit="PIECE",
        quantity=2,
        precision=0,
        unit_price_cents=1000,
        min_charge_cents=0,
        min_quantity=0,
        extras_cents=100,
        express=True,
        express_surcharge_cents=250,
        same_day=False,
        same_day_surcharge_cents=None,
        special=False,
        special_surcharge_cents=None,
        discount_cents=0,
        discount_authorized=False,
        allow_zero_rate=False,
        tax_category="STANDARD",
        rate_bps=500,
        price_includes_tax=False,
    )
    assert piece.merchandise_cents == 2000
    assert piece.tax_cents == 118
    assert piece.total_cents == 2468
    weighed = quote(
        unit="KG",
        quantity=1250,
        precision=3,
        unit_price_cents=1000,
        min_charge_cents=2000,
        min_quantity=1000,
        extras_cents=0,
        express=False,
        express_surcharge_cents=None,
        same_day=False,
        same_day_surcharge_cents=None,
        special=False,
        special_surcharge_cents=None,
        discount_cents=0,
        discount_authorized=False,
        allow_zero_rate=False,
        tax_category="STANDARD",
        rate_bps=0,
        price_includes_tax=False,
    )
    assert weighed.minimum_charge_applied is True
    assert weighed.total_cents == 2000


def test_quote_rejects_bad_quantity_rate_discount_and_missing_surcharge() -> None:
    common = dict(
        unit="PIECE",
        precision=0,
        unit_price_cents=500,
        min_charge_cents=0,
        min_quantity=0,
        extras_cents=0,
        express=False,
        express_surcharge_cents=None,
        same_day=False,
        same_day_surcharge_cents=None,
        special=False,
        special_surcharge_cents=None,
        discount_cents=0,
        discount_authorized=False,
        allow_zero_rate=False,
        tax_category="STANDARD",
        rate_bps=0,
        price_includes_tax=False,
    )
    for change, code in (
        ({"quantity": -1}, "invalid_quantity"),
        ({"quantity": 1, "unit_price_cents": 0}, "invalid_rate"),
        ({"quantity": 1, "unit": "BOX"}, "invalid_unit"),
        ({"quantity": 1, "discount_cents": 10}, "discount_unauthorized"),
        ({"quantity": 1, "express": True}, "surcharge_unavailable"),
    ):
        try:
            quote(**{**common, "quantity": 1, **change})
        except LaundryPriceError as exc:
            assert exc.code == code
        else:
            raise AssertionError(code)


def test_catalog_quote_keeps_branch_customer_and_date_rules(client, session) -> None:
    headers = _login(client)
    closed = client.get("/api/v1/laundry/services", headers=headers)
    assert closed.status_code == 403
    _laundry(client, headers)
    client.put(
        "/api/v1/settings/tax",
        headers=headers,
        json={
            "vat_registered": True,
            "trn": "100123456700003",
            "legal_name": "Laundry Test",
            "prices_include_vat": False,
            "standard_rate_bps": 500,
        },
    )
    applied = client.post("/api/v1/laundry/templates/laundry_shop", headers=headers)
    assert applied.status_code == 200, applied.text
    assert applied.json()["tracking_mode"] == "bag"
    services = client.get("/api/v1/laundry/services", headers=headers).json()
    shirt = next(row for row in services if row["code"] == "dry_clean_shirt")
    shop = Store(code="A", name="Shop A", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    other = Store(code="B", name="Shop B", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    customer = Customer(code="HOTEL", name="Hotel", tenant_id=DEFAULT_TENANT_ID)
    stranger = Customer(code="OTHER", name="Other", tenant_id=DEFAULT_TENANT_ID)
    session.add_all([shop, other, customer, stranger])
    session.commit()
    today = date.today().isoformat()
    lists = {
        "branch": {"kind": "branch", "store_id": str(shop.id), "customer_id": None},
        "customer": {"kind": "customer", "store_id": None, "customer_id": str(customer.id)},
        "expired": {
            "kind": "standard",
            "store_id": None,
            "customer_id": None,
            "valid_to": (date.today() - timedelta(days=1)).isoformat(),
        },
    }
    made = {}
    for code, extra in lists.items():
        body = {"code": code, "name": code, "valid_from": None, "valid_to": None, **extra}
        response = client.post("/api/v1/laundry/price-lists", headers=headers, json=body)
        assert response.status_code == 200, response.text
        made[code] = response.json()["id"]
        rated = client.put(
            f"/api/v1/laundry/price-lists/{made[code]}/rates",
            headers=headers,
            json={"service_id": shirt["id"], "unit_price_cents": 1500},
        )
        assert rated.status_code == 200, rated.text
    priced = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={
            "service_id": shirt["id"],
            "quantity": 2,
            "on": today,
            "price_list_id": made["branch"],
            "store_id": str(shop.id),
        },
    )
    assert priced.status_code == 200, priced.text
    assert priced.json()["total_cents"] == 3150
    wrong_branch = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={
            "service_id": shirt["id"],
            "quantity": 1,
            "on": today,
            "price_list_id": made["branch"],
            "store_id": str(other.id),
        },
    )
    assert wrong_branch.status_code == 422
    assert wrong_branch.json()["error"]["code"] == "expired_price_list"
    wrong_customer = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={
            "service_id": shirt["id"],
            "quantity": 1,
            "on": today,
            "price_list_id": made["customer"],
            "customer_id": str(stranger.id),
        },
    )
    assert wrong_customer.json()["error"]["code"] == "expired_price_list"
    expired = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={"service_id": shirt["id"], "quantity": 1, "on": today, "price_list_id": made["expired"]},
    )
    assert expired.json()["error"]["code"] == "expired_price_list"
    client.put(
        "/api/v1/laundry/settings",
        headers=headers,
        json={
            "operating_modes": ["WASH_AND_FOLD"],
            "tracking_mode": "bag",
            "weight_precision": 3,
            "express_daily_capacity": 0,
        },
    )
    blocked = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={"service_id": shirt["id"], "quantity": 1, "on": today, "express": True},
    )
    assert blocked.json()["error"]["code"] == "express_capacity"


def test_net_weight_rejects_negative_and_zero() -> None:
    assert net_weight(2500, 250) == 2250
    for gross, tare in ((-1, 0), (0, 0), (100, 100), (50, 80)):
        try:
            net_weight(gross, tare)
        except LaundryPriceError as exc:
            assert exc.code == "invalid_quantity"
        else:
            raise AssertionError((gross, tare))


def test_branch_capacity_overrides_the_tenant_and_a_future_list_is_refused(client, session) -> None:
    headers = _login(client)
    _laundry(client, headers)
    applied = client.post("/api/v1/laundry/templates/laundry_dry_cleaner", headers=headers)
    assert applied.status_code == 200, applied.text
    shirt = next(
        row
        for row in client.get("/api/v1/laundry/services", headers=headers).json()
        if row["code"] == "dry_clean_shirt"
    )
    edited = client.patch(
        f"/api/v1/laundry/services/{shirt['id']}",
        headers=headers,
        json={"name": "Dry clean dress shirt", "base_rate_cents": 2000, "allow_zero_rate": False},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Dry clean dress shirt"
    service = session.get(LaundryService, uuid.UUID(shirt["id"]))
    assert service is not None
    service.express_surcharge_cents = 100
    session.commit()
    shop = Store(code="CAP-A", name="Capacity A", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    other = Store(code="CAP-B", name="Capacity B", currency="AED", tenant_id=DEFAULT_TENANT_ID)
    session.add_all([shop, other])
    session.commit()
    closed = client.put(
        f"/api/v1/laundry/branches/{shop.id}/express-capacity",
        headers=headers,
        json={"express_daily_capacity": 0},
    )
    assert closed.status_code == 200, closed.text
    today = date.today().isoformat()
    blocked = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={"service_id": shirt["id"], "quantity": 1, "on": today, "store_id": str(shop.id), "express": True},
    )
    assert blocked.json()["error"]["code"] == "express_capacity"
    open_branch = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={"service_id": shirt["id"], "quantity": 1, "on": today, "store_id": str(other.id), "express": True},
    )
    assert open_branch.status_code == 200, open_branch.text
    future = client.post(
        "/api/v1/laundry/price-lists",
        headers=headers,
        json={
            "code": "later",
            "name": "Later",
            "kind": "standard",
            "store_id": None,
            "customer_id": None,
            "valid_from": (date.today() + timedelta(days=2)).isoformat(),
            "valid_to": None,
        },
    )
    assert future.status_code == 200, future.text
    client.put(
        f"/api/v1/laundry/price-lists/{future.json()['id']}/rates",
        headers=headers,
        json={"service_id": shirt["id"], "unit_price_cents": 900},
    )
    refused = client.post(
        "/api/v1/laundry/quotes",
        headers=headers,
        json={"service_id": shirt["id"], "quantity": 1, "on": today, "price_list_id": future.json()["id"]},
    )
    assert refused.json()["error"]["code"] == "expired_price_list"
