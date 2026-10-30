"""Branch tax follows the selling branch and stays on the sale after settings change."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Sale
from app.services.tax import line_tax
from test_returns import CABLE_ID, CASHIER_ID, STORE_ID, admin_token, bearer, push, record_sale, seed_catalog

OTHER = "00000000-0000-4000-8000-000000000099"


def _tax(client, store_id: str, body: dict, token: str):
    return client.put(f"/api/v1/stores/{store_id}/tax", headers=bearer(token), json=body)


def test_country_fields_differ_and_rates_do_not_cross_branches(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    pakistan = client.get("/api/v1/settings/country-tax/PK")
    assert pakistan.status_code == 200, pakistan.text
    meta = pakistan.json()
    assert meta["registration_label"] == "NTN"
    assert meta["secondary_registration_label"] == "Sales tax registration number (STRN)"
    assert meta["legal_local_language"] == "ur"
    assert meta["legal_local_label"] == "Legal name (Urdu)"
    assert meta["rate_known"] is False

    emirates = client.get("/api/v1/settings/country-tax/AE").json()
    assert emirates["registration_label"] == "TRN"
    assert emirates["legal_local_language"] == "ar"
    assert emirates["rate_known"] is True
    assert emirates["standard_rate_bps"] == 500

    saudi = client.get("/api/v1/settings/country-tax/SA").json()
    assert saudi["registration_label"] == "VAT registration number"
    assert saudi["legal_local_language"] == "ar"

    saved = _tax(
        client,
        STORE_ID,
        {
            "country": "PK",
            "city": "Lahore",
            "region": "Punjab",
            "registered": True,
            "registration_number": "1234567",
            "secondary_registration_number": "32-77-0000-000-00",
            "legal_name": "Rehhas Attire",
            "legal_name_local": "ریہاس",
            "prices_include_vat": False,
            "standard_rate_bps": 500,
        },
        token,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["country_tax"]["legal_local_language"] == "ur"
    assert saved.json()["legal_entity_id"]

    assert (
        push(
            client,
            "store",
            {"id": OTHER, "code": "DXB-01", "name": "Dubai", "currency": "USD"},
        ).status_code
        == 200
    )
    dubai = _tax(
        client,
        OTHER,
        {
            "country": "AE",
            "city": "Dubai",
            "region": "DXB",
            "registered": True,
            "registration_number": "100000000000003",
            "legal_name": "Rehhas Attire",
            "legal_name_local": "رهاس",
            "prices_include_vat": True,
            "standard_rate_bps": 500,
        },
        token,
    )
    assert dubai.status_code == 200, dubai.text
    assert dubai.json()["legal_entity_id"] != saved.json()["legal_entity_id"]

    lahore = client.post(
        f"/api/v1/stores/{STORE_ID}/tax/preview",
        headers=bearer(token),
        json={"amount_cents": 10000, "category": "STANDARD"},
    ).json()
    expected = line_tax(10000, 1, 500, inclusive=False)
    assert (lahore["net_cents"], lahore["tax_cents"], lahore["total_cents"]) == (
        expected.net_cents,
        expected.tax_cents,
        expected.line_total_cents,
    )
    gulf = client.post(
        f"/api/v1/stores/{OTHER}/tax/preview",
        headers=bearer(token),
        json={"amount_cents": 10000, "category": "STANDARD"},
    ).json()
    inclusive = line_tax(10000, 1, 500, inclusive=True)
    assert gulf["tax_cents"] == inclusive.tax_cents
    assert gulf["total_cents"] == 10000

    changed = _tax(
        client,
        STORE_ID,
        {
            "country": "PK",
            "city": "Lahore",
            "region": "Punjab",
            "registered": True,
            "registration_number": "1234567",
            "secondary_registration_number": "32-77-0000-000-00",
            "legal_name": "Rehhas Attire",
            "legal_name_local": "ریہاس",
            "prices_include_vat": False,
            "standard_rate_bps": 1700,
            "confirm_country_change": True,
        },
        token,
    )
    assert changed.status_code == 200, changed.text
    again = client.post(
        f"/api/v1/stores/{OTHER}/tax/preview",
        headers=bearer(token),
        json={"amount_cents": 10000, "category": "STANDARD"},
    ).json()
    assert again["tax_cents"] == gulf["tax_cents"]

    zero = client.post(
        f"/api/v1/stores/{STORE_ID}/tax/preview",
        headers=bearer(token),
        json={"amount_cents": 10000, "category": "ZERO"},
    ).json()
    exempt = client.post(
        f"/api/v1/stores/{STORE_ID}/tax/preview",
        headers=bearer(token),
        json={"amount_cents": 10000, "category": "EXEMPT"},
    ).json()
    assert zero["tax_cents"] == 0 and exempt["tax_cents"] == 0
    assert zero["category"] != exempt["category"]

    missing = client.get(f"/api/v1/stores/{uuid.uuid4()}/tax", headers=bearer(token))
    assert missing.status_code == 404

    blocked = client.patch(
        f"/api/v1/stores/{STORE_ID}",
        headers=bearer(token),
        json={"country": "GB", "confirm_country_change": False},
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "country_change_confirmation"

    moved = client.patch(
        f"/api/v1/stores/{STORE_ID}",
        headers=bearer(token),
        json={"country": "GB", "confirm_country_change": True},
    )
    assert moved.status_code == 200, moved.text
    refused = push(
        client,
        "sale",
        {
            "id": str(uuid.uuid4()),
            "store_id": STORE_ID,
            "cashier_id": CASHIER_ID,
            "currency": "USD",
            "payment_method": "cash",
            "subtotal_cents": 1000,
            "tax_cents": 0,
            "total_cents": 1000,
            "client_sale_id": str(uuid.uuid4()),
            "items": [
                {
                    "id": str(uuid.uuid4()),
                    "product_id": CABLE_ID,
                    "quantity": 1,
                    "unit_price_cents": 1000,
                    "tax_cents": 0,
                    "line_total_cents": 1000,
                }
            ],
        },
    )
    assert refused.status_code == 422
    assert "Confirm this branch" in refused.text

    _tax(
        client,
        STORE_ID,
        {
            "country": "PK",
            "city": "Lahore",
            "registered": True,
            "registration_number": "1234567",
            "legal_name": "Rehhas Attire",
            "legal_name_local": "ریہاس",
            "prices_include_vat": False,
            "standard_rate_bps": 500,
            "confirm_country_change": True,
        },
        token,
    )
    record_sale(client, product_id=CABLE_ID, price=1500)
    sale = session.scalars(select(Sale).order_by(Sale.created_at.desc())).first()
    assert sale is not None and sale.tax_snapshot is not None
    assert sale.tax_snapshot["country"] == "PK"
    assert sale.tax_snapshot["standard_rate_bps"] == 500
    frozen = dict(sale.tax_snapshot)
    _tax(
        client,
        STORE_ID,
        {
            "country": "PK",
            "city": "Lahore",
            "registered": True,
            "registration_number": "1234567",
            "legal_name": "Rehhas Attire Renamed",
            "prices_include_vat": False,
            "standard_rate_bps": 1800,
            "confirm_country_change": True,
        },
        token,
    )
    session.refresh(sale)
    assert sale.tax_snapshot == frozen
    assert session.scalar(select(AuditLog).where(AuditLog.action == "settings.branch_tax")) is not None
