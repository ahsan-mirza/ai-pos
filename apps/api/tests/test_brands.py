from tests.test_inventory import CABLE, DT, STORE_MANAGER_ROLE, admin, event, push, seed
from tests.test_manual_adjustments import portal_user

PIXEL_PRO = "00000000-0000-4000-8000-000000000099"


def sub_category(client, headers, category: str, sub: str) -> tuple[str, str]:
    for row in client.get("/api/v1/categories", headers=headers).json():
        if row["name"] == category:
            for item in row["sub_categories"]:
                if item["name"] == sub:
                    return row["id"], item["id"]
    raise AssertionError(f"{category} > {sub} not found")


def test_sync_brand_text_becomes_a_linked_global_brand(client) -> None:
    seed(client)
    headers = admin(client)
    pushed = push(
        client,
        [
            event(
                "product-pixel-pro",
                "product",
                {
                    "id": PIXEL_PRO,
                    "store_id": DT,
                    "sku": "GOO-PIXEL9P",
                    "barcode": "2000000010304",
                    "name": "Pixel 9 Pro",
                    "brand": " google ",
                    "category": "Phones",
                    "sub_category": "Smartphones",
                    "price_cents": 429900,
                    "currency": "USD",
                    "is_serialized": True,
                    "stock_quantity": 0,
                },
            )
        ],
    )
    assert pushed.status_code == 200, pushed.text
    _, smartphones = sub_category(client, headers, "Phones", "Smartphones")
    product = client.get(f"/api/v1/products/{PIXEL_PRO}", headers=headers).json()
    assert product["brand"] == "google"
    brands = client.get("/api/v1/brands", headers=headers, params={"sub_category_id": smartphones}).json()
    assert [brand["name"] for brand in brands] == ["google"]
    assert product["brand_id"] == brands[0]["id"]
    assert brands[0]["product_count"] == 1


def test_brand_model_variant_hierarchy(client) -> None:
    seed(client)
    headers = admin(client)
    phones, smartphones = sub_category(client, headers, "Phones", "Smartphones")
    accessories, cables = sub_category(client, headers, "Accessories", "Cables")

    apple = client.post("/api/v1/brands", headers=headers, json={"name": "Apple"})
    assert apple.status_code == 201, apple.text
    apple_id = apple.json()["id"]
    assert client.post("/api/v1/brands", headers=headers, json={"name": "apple"}).status_code == 409

    model = client.post(
        "/api/v1/product-models",
        headers=headers,
        json={"brand_id": apple_id, "sub_category_id": smartphones, "name": "iPhone 16 Pro", "release_year": 2024},
    )
    assert model.status_code == 201, model.text
    model_id = model.json()["id"]
    assert model.json()["category_name"] == "Phones"
    linked = client.get("/api/v1/brands", headers=headers, params={"sub_category_id": smartphones}).json()
    assert apple_id in {brand["id"] for brand in linked}

    variant = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "APL-IP16P-256-DST",
            "barcode": "2000000010205",
            "name": "iPhone 16 Pro 256GB Desert Titanium",
            "product_model_id": model_id,
            "variant_attributes": {"Storage": "256GB", "color": " Desert Titanium ", "ram": ""},
            "price_cents": 469900,
            "is_serialized": True,
        },
    )
    assert variant.status_code == 201, variant.text
    body = variant.json()
    assert body["category_id"] == phones
    assert body["sub_category_id"] == smartphones
    assert body["brand_id"] == apple_id
    assert body["brand"] == "Apple"
    assert body["model_name"] == "iPhone 16 Pro"
    assert body["variant_attributes"] == {"storage": "256GB", "color": "Desert Titanium"}

    listed = client.get("/api/v1/products", headers=headers, params={"product_model_id": model_id}).json()
    assert [item["sku"] for item in listed] == ["APL-IP16P-256-DST"]
    models = client.get("/api/v1/product-models", headers=headers, params={"brand_id": apple_id}).json()
    assert models[0]["variant_count"] == 1

    mismatch = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "APL-WRONG",
            "barcode": "2000000010212",
            "name": "Wrong",
            "product_model_id": model_id,
            "category_id": accessories,
            "price_cents": 100,
        },
    )
    assert mismatch.status_code == 422
    assert mismatch.json()["error"]["code"] == "model_mismatch"

    moved = client.patch(
        f"/api/v1/products/{body['id']}", headers=headers, json={"sub_category_id": cables, "category_id": accessories}
    )
    assert moved.status_code == 422
    detached = client.patch(
        f"/api/v1/products/{body['id']}",
        headers=headers,
        json={"product_model_id": None, "category_id": accessories, "sub_category_id": cables},
    )
    assert detached.status_code == 200, detached.text
    assert detached.json()["product_model_id"] is None
    assert detached.json()["brand"] == "Apple"
    attached = client.patch(f"/api/v1/products/{body['id']}", headers=headers, json={"product_model_id": model_id})
    assert attached.json()["sub_category_id"] == smartphones

    assert client.delete(f"/api/v1/product-models/{model_id}", headers=headers).status_code == 409
    assert client.delete(f"/api/v1/brands/{apple_id}", headers=headers).status_code == 409
    assert client.delete(f"/api/v1/brands/{apple_id}/sub-categories/{smartphones}", headers=headers).status_code == 409

    renamed = client.patch(f"/api/v1/brands/{apple_id}", headers=headers, json={"name": "Apple Inc"})
    assert renamed.status_code == 200
    assert client.get(f"/api/v1/products/{body['id']}", headers=headers).json()["brand"] == "Apple Inc"


def test_store_bound_manager_can_read_but_not_change_brands(client) -> None:
    seed(client)
    headers = admin(client)
    manager = portal_user(client, headers, "brandmgr", STORE_MANAGER_ROLE, DT)
    assert client.get("/api/v1/brands", headers=manager).status_code == 200
    blocked = client.post("/api/v1/brands", headers=manager, json={"name": "Nokia"})
    assert blocked.status_code == 403
    assert client.get(f"/api/v1/products/{CABLE}", headers=manager).json()["brand_id"] is None
