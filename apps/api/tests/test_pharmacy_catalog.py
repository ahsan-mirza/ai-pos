"""Pharmacy catalogue: profile, taxonomy, medicine master, and the seven existing profiles."""

import uuid

from sqlalchemy import select

from app.core import capabilities as catalog
from app.models.audit_log import AuditLog
from app.models.pharmacy import PharmacyProductDetails, ProductIngredient
from app.models.product import Product
from app.services.taxonomy_service import ensure_taxonomy
from app.tenancy.scoping import DEFAULT_TENANT_ID, INCLUDE_ALL
from tests.test_capabilities import change_profile
from tests.test_inventory import ADMIN_PASSWORD

OTHER_TENANT = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
PROFILES = (
    "electronics_wholesale",
    "wholesale_retail",
    "retail_fashion",
    "grocery",
    "restaurant",
    "cafe",
    "quick_service",
)


def _admin(client) -> dict[str, str]:
    response = client.post("/api/v1/auth/login-password", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _pharmacy(client) -> dict[str, str]:
    headers = _admin(client)
    switched = change_profile(client, headers, "pharmacy")
    assert switched.status_code == 200, switched.text
    assert switched.json()["business_profile"] == "pharmacy"
    assert "pharmacy_catalog" in switched.json()["capabilities"]
    return headers


def _medicine(**overrides) -> dict:
    body = {
        "product_kind": "MEDICINE",
        "dispensing_class": "PRESCRIPTION",
        "generic_name": "Amoxicillin",
        "manufacturer": "Example Pharma",
        "dosage_form": "tablet",
        "route": "oral",
        "strength_amount": "500",
        "strength_unit": "mg",
        "pack_size_label": "10 tablets",
        "units_per_pack": 1,
        "base_unit_code": "PIECE",
        "selling_unit_code": "PIECE",
        "price_control": "NONE",
        "ingredients": [
            {"name": "Amoxicillin", "strength_amount": "500", "strength_unit": "mg", "is_active_ingredient": True},
            {"name": "Clavulanic acid", "strength_amount": "125", "strength_unit": "mg", "is_active_ingredient": True},
        ],
    }
    body.update(overrides)
    return body


def _shelf(client, headers, name: str) -> str:
    created = client.post("/api/v1/categories", headers=headers, json={"name": name})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _create(client, headers, name: str, pharmacy: dict | None, **extra) -> object:
    body = {
        "sku": extra.pop("sku", f"SKU-{name[:12]}"),
        "barcode": extra.pop("barcode", f"629{abs(hash(name)) % 10**10:010d}"[:13]),
        "name": name,
        "price_cents": 1500,
        "brand": extra.pop("brand", "Example"),
    }
    body.update(extra)
    if pharmacy is not None:
        body["pharmacy"] = pharmacy
    if "category_id" not in body and "product_model_id" not in body:
        body["category_id"] = _shelf(client, headers, f"Shelf {body['sku']}")
    return client.post("/api/v1/inventory/products", headers=headers, json=body)


def test_pharmacy_is_a_profile_and_the_seven_profiles_remain() -> None:
    assert set(catalog.SUB_TYPES["pharmacy"]) == {"community_pharmacy"}
    assert catalog.PROFILES["pharmacy"][-1].value == "pharmacy_catalog"
    for profile in PROFILES:
        assert profile in catalog.PROFILES
        assert profile != "pharmacy"


def test_pharmacy_profile_can_be_selected(client) -> None:
    _pharmacy(client)


def test_pharmacy_taxonomy_keeps_veterinary_inactive(client, session) -> None:
    headers = _pharmacy(client)
    added = ensure_taxonomy(session, "pharmacy")
    assert added > 0
    session.commit()
    listed = client.get("/api/v1/categories", headers=headers)
    assert listed.status_code == 200, listed.text
    by_code = {row["code"]: row for row in listed.json()}
    for code in ("RX", "OTC", "VIT", "DEV", "SUP", "BABY", "CARE", "COS", "NUT", "VET", "ACC"):
        assert code in by_code
    assert by_code["VET"]["is_active"] is False
    assert by_code["OTC"]["sub_categories"]
    active = client.get("/api/v1/categories?active_only=true", headers=headers)
    assert "VET" not in {row["code"] for row in active.json()}
    child = client.post(
        f"/api/v1/categories/{by_code['VET']['id']}/sub-categories",
        headers=headers,
        json={"name": "Extra veterinary"},
    )
    assert child.status_code == 422
    assert child.json()["error"]["code"] == "category_inactive"
    refused = client.patch(f"/api/v1/categories/{by_code['VET']['id']}", headers=headers, json={"is_active": True})
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "veterinary_not_licensed"


def test_create_update_and_read_a_pharmacy_product(client, session) -> None:
    headers = _pharmacy(client)
    ensure_taxonomy(session, "pharmacy")
    session.commit()
    categories = client.get("/api/v1/categories?active_only=true", headers=headers).json()
    otc = next(row for row in categories if row["code"] == "OTC")
    created = _create(
        client,
        headers,
        "Amoxiclav 500",
        _medicine(),
        sku="AMOX-500",
        barcode="6290000000017",
        category_id=otc["id"],
        sub_category_id=otc["sub_categories"][0]["id"],
    )
    assert created.status_code == 201, created.text
    product_id = created.json()["id"]
    assert created.json()["price_cents"] == 1500
    detail = client.get(f"/api/v1/pharmacy/products/{product_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["dispensing_class"] == "PRESCRIPTION"
    assert body["classification_source"] == "TENANT_DECLARED"
    assert [row["name"] for row in body["ingredients"]] == ["Amoxicillin", "Clavulanic acid"]
    assert body["lot_on_product_master"] is False
    assert body["official_price_state"] == "NOT_REQUIRED"
    assert body["sale_blocked"] is False
    found = client.get("/api/v1/products/search", headers=headers, params={"q": "Amoxicillin"})
    assert found.status_code == 200, found.text
    assert any(row["product"]["id"] == product_id for row in found.json())
    updated = client.patch(
        f"/api/v1/pharmacy/products/{product_id}",
        headers=headers,
        json={"pharmacy": _medicine(generic_name="Amoxicillin trihydrate", price_control="MINIMUM")},
    )
    assert updated.status_code == 200, updated.text
    again = client.get(f"/api/v1/pharmacy/products/{product_id}", headers=headers).json()
    assert again["generic_name"] == "Amoxicillin trihydrate"
    assert again["official_price_state"] == "MISSING"
    assert again["sale_blocked"] is True
    audited = session.scalars(select(AuditLog).where(AuditLog.action == "pharmacy.dispensing_class")).all()
    assert audited


def test_pharmacy_validation_rules(client) -> None:
    headers = _pharmacy(client)
    missing_class = _create(client, headers, "No class", _medicine())
    missing_class_body = _medicine()
    del missing_class_body["dispensing_class"]
    refused = _create(client, headers, "No class", missing_class_body, sku="NO-CLASS", barcode="6290000000024")
    assert refused.status_code == 422, refused.text
    veterinary = _create(
        client,
        headers,
        "Animal tablet",
        _medicine(product_kind="VETERINARY"),
        sku="VET-1",
        barcode="6290000000031",
    )
    assert veterinary.status_code == 422
    assert veterinary.json()["error"]["code"] == "veterinary_not_licensed"
    fraction = _create(
        client,
        headers,
        "Half pack",
        _medicine(fractional_dispensing_allowed=True),
        sku="HALF",
        barcode="6290000000048",
    )
    assert fraction.status_code == 422
    assert fraction.json()["error"]["code"] == "fractional_dispensing"
    bad_pack = _create(
        client,
        headers,
        "Wrong box",
        _medicine(selling_unit_code="BOX_10", units_per_pack=9),
        sku="BOX-9",
        barcode="6290000000055",
    )
    assert bad_pack.status_code == 422
    assert bad_pack.json()["error"]["code"] == "pack_factor"
    priced = _create(
        client,
        headers,
        "Priced box",
        _medicine(selling_unit_code="BOX_10", units_per_pack=10, price_control="NONE", min_price_cents=100),
        sku="BOX-10",
        barcode="6290000000062",
    )
    assert priced.status_code == 422
    assert priced.json()["error"]["code"] == "price_control"
    no_ingredient = _create(
        client,
        headers,
        "Empty formula",
        _medicine(ingredients=[]),
        sku="EMPTY",
        barcode="6290000000079",
    )
    assert no_ingredient.status_code == 422
    assert no_ingredient.json()["error"]["code"] == "ingredient"
    assert missing_class.status_code == 201


def test_tenant_isolation_and_anonymous_rejection(client, session) -> None:
    headers = _pharmacy(client)
    created = _create(client, headers, "Tenant A tablet", _medicine(), sku="TENANT-A", barcode="6290000000086")
    assert created.status_code == 201, created.text
    own_id = created.json()["id"]
    foreign_id = uuid.uuid4()
    session.info[INCLUDE_ALL] = True
    session.add(
        Product(
            id=foreign_id,
            tenant_id=OTHER_TENANT,
            sku="TENANT-B",
            barcode="6290000000093",
            name="Tenant B tablet",
            category="OTC",
            price_cents=100,
            currency="AED",
            generic_name="Hidden",
        )
    )
    session.flush()
    session.add(
        PharmacyProductDetails(
            product_id=foreign_id,
            tenant_id=OTHER_TENANT,
            product_kind="SUPPLY",
            dispensing_class="OTC",
            units_per_pack=1,
        )
    )
    session.commit()
    session.info.pop(INCLUDE_ALL, None)
    hidden = client.get(f"/api/v1/pharmacy/products/{foreign_id}", headers=headers)
    assert hidden.status_code == 404
    listed = client.get("/api/v1/pharmacy/products", headers=headers).json()
    assert own_id in {row["product_id"] for row in listed}
    assert foreign_id not in {row["product_id"] for row in listed}
    anonymous = client.get(f"/api/v1/pharmacy/products/{own_id}")
    assert anonymous.status_code == 401
    session.info[INCLUDE_ALL] = True
    assert session.get(Product, foreign_id) is not None
    assert session.scalars(select(ProductIngredient).where(ProductIngredient.product_id == foreign_id)).all() == []
    session.info.pop(INCLUDE_ALL, None)
    assert session.get(Product, foreign_id) is None


def test_other_profiles_still_create_products_and_reject_pharmacy_fields(client) -> None:
    headers = _admin(client)
    for index, profile in enumerate(PROFILES):
        switched = change_profile(client, headers, profile)
        assert switched.status_code == 200, switched.text
        created = _create(
            client,
            headers,
            f"{profile} item",
            None,
            sku=f"REG-{index}",
            barcode=f"50000000000{index}",
        )
        assert created.status_code == 201, created.text
        leaked = _create(
            client,
            headers,
            f"{profile} leak",
            _medicine(),
            sku=f"LEAK-{index}",
            barcode=f"51000000000{index}",
        )
        assert leaked.status_code == 422
        assert leaked.json()["error"]["code"] == "profile_not_pharmacy"
    pharmacy = change_profile(client, headers, "pharmacy")
    assert pharmacy.status_code == 200
    blocked = client.get("/api/v1/pharmacy/products", headers=headers)
    assert blocked.status_code == 200


def test_existing_product_payload_stays_stable_for_the_register(client) -> None:
    headers = _pharmacy(client)
    created = _create(client, headers, "Register tablet", _medicine(), sku="POS-1", barcode="6290000000109")
    assert created.status_code == 201, created.text
    product = client.get(f"/api/v1/products/{created.json()['id']}", headers=headers)
    assert product.status_code == 200, product.text
    body = product.json()
    assert body["sku"] == "POS-1"
    assert body["barcode"] == "6290000000109"
    assert body["price_cents"] == 1500
    assert "pharmacy" not in body
    assert DEFAULT_TENANT_ID
