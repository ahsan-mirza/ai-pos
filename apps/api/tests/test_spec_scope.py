"""A business type can save only its own specification keys. Another type is never a fallback."""

from app.core.capabilities import PROFILE_LABELS
from app.core.spec_scope import foreign_specification_keys
from wholesale_support import admin


def test_every_profile_rejects_another_types_attributes() -> None:
    assert set(PROFILE_LABELS) == {
        "electronics_wholesale",
        "wholesale_retail",
        "retail_fashion",
        "grocery",
        "restaurant",
        "cafe",
        "quick_service",
    }
    assert "services" not in PROFILE_LABELS
    cases = {
        "restaurant": ["battery", "ram", "fabric", "milk_type", "net_weight"],
        "quick_service": ["battery", "fabric", "milk_type"],
        "cafe": ["battery", "patty_type", "fabric", "net_weight"],
        "grocery": ["battery", "patty_type", "fabric", "milk_type"],
        "retail_fashion": ["battery", "patty_type", "milk_type", "net_weight"],
        "electronics_wholesale": ["patty_type", "milk_type", "fabric", "net_weight"],
        "wholesale_retail": ["battery", "patty_type", "fabric", "milk_type", "net_weight"],
    }
    categories = {
        "restaurant": "Burgers",
        "quick_service": "Burgers",
        "cafe": "Hot coffee",
        "grocery": "Dairy",
        "retail_fashion": "Dresses",
        "electronics_wholesale": "Smartphones",
        "wholesale_retail": "General",
    }
    for profile, foreign in cases.items():
        assert foreign_specification_keys(profile, foreign, category=categories[profile]) == foreign
    burger = foreign_specification_keys(
        "restaurant", ["patty_type", "spice_level", "house_note"], category="Burgers"
    )
    assert burger == []
    assert foreign_specification_keys("electronics_wholesale", ["battery", "storage"], category="Smartphones") == []
    assert foreign_specification_keys("electronics_wholesale", ["battery"], category="Burgers") == ["battery"]
    assert foreign_specification_keys("electronics_wholesale", ["processor"], category="Laptops") == []
    assert foreign_specification_keys("electronics_wholesale", ["battery"], category="Laptops") == ["battery"]
    assert foreign_specification_keys("cafe", ["milk_type", "caffeine"], category="Hot coffee") == []
    assert foreign_specification_keys("grocery", ["net_weight", "origin"], category="Dairy") == []
    assert foreign_specification_keys("retail_fashion", ["size", "fabric"], category="Dresses") == []
    assert foreign_specification_keys("restaurant", ["battery"], category="Phones") == ["battery"]
    assert foreign_specification_keys(None, ["battery"], category="Smartphones") == ["battery"]
    unknown = foreign_specification_keys("services", ["battery", "patty_type"], category="Burgers")
    assert unknown == ["battery", "patty_type"]


def test_restaurant_cannot_save_battery_capacity(client) -> None:
    headers, _ = admin(client)
    phones = client.post("/api/v1/categories", headers=headers, json={"name": "Phones"}).json()
    burgers = client.post("/api/v1/categories", headers=headers, json={"name": "Burgers"}).json()
    electronics = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "PHONE-1",
            "barcode": "100000000101",
            "name": "Handset",
            "category_id": phones["id"],
            "price_cents": 100,
            "specifications": {"battery": "5000mAh"},
        },
    )
    assert electronics.status_code == 201, electronics.text
    misplaced = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "BURGER-ELEC",
            "barcode": "100000000104",
            "name": "Classic Burger",
            "category_id": burgers["id"],
            "price_cents": 2900,
            "specifications": {"battery": "5000mAh"},
        },
    )
    assert misplaced.status_code == 422
    assert misplaced.json()["error"]["code"] == "spec_not_for_business"

    switched = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "restaurant", "capabilities": None},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["business_profile"] == "restaurant"

    rejected = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "BURGER-BAT",
            "barcode": "100000000102",
            "name": "Classic Burger",
            "category_id": burgers["id"],
            "price_cents": 2900,
            "specifications": {"battery": "5000mAh"},
            "business_profile": "electronics_wholesale",
        },
    )
    assert rejected.status_code == 422

    blocked = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "BURGER-BAT",
            "barcode": "100000000102",
            "name": "Classic Burger",
            "category_id": burgers["id"],
            "price_cents": 2900,
            "specifications": {"battery": "5000mAh", "patty_type": "Beef"},
        },
    )
    assert blocked.status_code == 422
    assert blocked.json()["error"]["code"] == "spec_not_for_business"

    created = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "BURGER-1",
            "barcode": "100000000103",
            "name": "Classic Burger",
            "category_id": burgers["id"],
            "price_cents": 2900,
            "specifications": {"patty_type": "Beef", "spice_level": "Mild", "house_note": "No onions"},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["specifications"]["patty_type"] == "Beef"
    assert "battery" not in created.json()["specifications"]

    kept = client.patch(
        f"/api/v1/products/{created.json()['id']}",
        headers=headers,
        json={"specifications": {"battery": "5000mAh"}},
    )
    assert kept.status_code == 422
    assert kept.json()["error"]["code"] == "spec_not_for_business"
    current = client.get(f"/api/v1/products/{created.json()['id']}", headers=headers)
    assert current.status_code == 200
    assert current.json()["specifications"]["patty_type"] == "Beef"
    assert "battery" not in current.json()["specifications"]
