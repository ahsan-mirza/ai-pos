import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.test_inventory import DT, STORE_MANAGER_ROLE, admin, bearer, device, seed

from app.models.audit_log import AuditLog
from app.models.brand import ProductModel
from app.models.category import Category
from app.tenancy.scoping import INCLUDE_ALL


def _pair(client, headers, name: str, sub_name: str) -> tuple[str, str]:
    created = client.post("/api/v1/categories", headers=headers, json={"name": name})
    assert created.status_code == 201, created.text
    category_id = created.json()["id"]
    with_sub = client.post(
        f"/api/v1/categories/{category_id}/sub-categories", headers=headers, json={"name": sub_name}
    )
    assert with_sub.status_code == 201, with_sub.text
    return category_id, with_sub.json()["sub_categories"][0]["id"]


def _model(client, headers, sub_id: str, name: str, brand_id: str | None = None) -> str:
    if brand_id is None:
        brand = client.post("/api/v1/brands", headers=headers, json={"name": f"Brand {name}"})
        assert brand.status_code == 201, brand.text
        brand_id = brand.json()["id"]
    created = client.post(
        "/api/v1/product-models",
        headers=headers,
        json={"brand_id": brand_id, "sub_category_id": sub_id, "name": name},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def test_an_empty_category_deletes_after_confirmation_data(client) -> None:
    headers = admin(client)
    category_id, _sub = _pair(client, headers, "Empty Shelf", "Unused")
    preview = client.get(f"/api/v1/categories/{category_id}/assigned-models", headers=headers)
    assert preview.status_code == 200, preview.text
    assert preview.json() == {"model_count": 0, "models": []}
    deleted = client.delete(f"/api/v1/categories/{category_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/categories/{category_id}/assigned-models", headers=headers).status_code == 404


def test_models_move_to_the_destination_and_the_product_follows(client, session) -> None:
    seed(client)
    headers = admin(client)
    source_id, source_sub = _pair(client, headers, "Handsets", "Phones")
    destination_id, destination_sub = _pair(client, headers, "Mobiles", "Phones")
    model_id = _model(client, headers, source_sub, "N1")
    listed = client.get(f"/api/v1/categories/{source_id}/assigned-models", headers=headers).json()
    assert listed["model_count"] == 1
    assert listed["models"][0]["name"] == "N1"
    assert listed["models"][0]["sub_category_name"] == "Phones"
    product = client.post(
        "/api/v1/inventory/products",
        headers=headers,
        json={
            "sku": "HAND-N1",
            "barcode": "2000000099001",
            "name": "N1 128GB",
            "product_model_id": model_id,
            "price_cents": 250000,
            "is_serialized": False,
        },
    )
    assert product.status_code == 201, product.text
    product_id = product.json()["id"]
    event_id = str(uuid.uuid4())
    moved = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": destination_id, "event_id": event_id},
    )
    assert moved.status_code == 204, moved.text
    again = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": destination_id, "event_id": event_id},
    )
    assert again.status_code == 204, again.text
    names = [row["name"] for row in client.get("/api/v1/categories", headers=headers).json()]
    assert "Handsets" not in names
    assert "Mobiles" in names
    saved = client.get(f"/api/v1/products/{product_id}", headers=headers).json()
    assert saved["category_id"] == destination_id
    assert saved["category"] == "Mobiles"
    assert saved["sub_category_id"] == destination_sub
    assert saved["price_cents"] == 250000
    assert saved["name"] == "N1 128GB"
    model = session.get(ProductModel, uuid.UUID(model_id))
    assert model is not None
    assert str(model.sub_category_id) == destination_sub
    actions = set(
        session.scalars(
            select(AuditLog.action).where(
                AuditLog.target_entity == "Category",
                AuditLog.target_entity_id == uuid.UUID(source_id),
            )
        )
    )
    assert "category.reassign_models" in actions
    assert "category.delete" in actions


def test_invalid_destination_is_rejected_and_the_model_stays(client, session) -> None:
    headers = admin(client)
    source_id, source_sub = _pair(client, headers, "Source", "Lines")
    model_id = _model(client, headers, source_sub, "Keep")
    same = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": source_id},
    )
    assert same.status_code == 422
    assert same.json()["error"]["code"] == "destination_invalid"
    assert "destination_category_id" in same.json()["error"]["details"]["fields"]
    bare = _pair(client, headers, "No Subs Yet", "Temp")
    client.delete(f"/api/v1/categories/sub-categories/{bare[1]}", headers=headers)
    missing_sub = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": bare[0]},
    )
    assert missing_sub.status_code == 422
    inactive = client.post("/api/v1/categories", headers=headers, json={"name": "Retired", "is_active": False})
    assert inactive.status_code == 201, inactive.text
    turned_off = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": inactive.json()["id"]},
    )
    assert turned_off.status_code == 422
    session.info[INCLUDE_ALL] = True
    foreign = Category(name="Other Tenant", code="OTHER-TENANT", description="", tenant_id=uuid.uuid4(), is_active=True)
    session.add(foreign)
    session.commit()
    session.info.pop(INCLUDE_ALL, None)
    foreign_id = str(foreign.id)
    crossed = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": foreign_id},
    )
    assert crossed.status_code == 422
    model = session.get(ProductModel, uuid.UUID(model_id))
    assert model is not None
    assert str(model.sub_category_id) == source_sub
    assert session.get(Category, uuid.UUID(source_id)) is not None


def test_a_name_clash_leaves_the_category(client, session) -> None:
    headers = admin(client)
    source_id, source_sub = _pair(client, headers, "From", "Shared")
    destination_id, destination_sub = _pair(client, headers, "To", "Shared")
    brand = client.post("/api/v1/brands", headers=headers, json={"name": "Shared Brand"})
    assert brand.status_code == 201, brand.text
    brand_id = brand.json()["id"]
    model_id = _model(client, headers, source_sub, "Twin", brand_id)
    _model(client, headers, destination_sub, "Twin", brand_id)
    clash = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": destination_id},
    )
    assert clash.status_code == 409, clash.text
    assert session.get(Category, uuid.UUID(source_id)) is not None
    assert str(session.get(ProductModel, uuid.UUID(model_id)).sub_category_id) == source_sub


def test_a_failed_commit_leaves_the_category(client, session, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = admin(client)
    source_id, source_sub = _pair(client, headers, "Pending", "Units")
    destination_id, _destination_sub = _pair(client, headers, "Ready", "Units")
    model_id = _model(client, headers, source_sub, "Solo")

    def fail_commit(*_args, **_kwargs):
        raise IntegrityError("COMMIT", {}, Exception("forced"))

    monkeypatch.setattr(session, "commit", fail_commit)
    failed = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers=headers,
        json={"destination_category_id": destination_id},
    )
    assert failed.status_code == 409, failed.text
    assert "left where they were" in failed.json()["error"]["message"]
    monkeypatch.undo()
    assert session.get(Category, uuid.UUID(source_id)) is not None
    assert str(session.get(ProductModel, uuid.UUID(model_id)).sub_category_id) == source_sub


def test_users_without_catalog_admin_cannot_move_a_category(client) -> None:
    seed(client)
    headers = admin(client)
    source_id, _sub = _pair(client, headers, "Guarded", "Items")
    destination_id, _dest = _pair(client, headers, "Open", "Items")
    cashier = client.post("/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device())
    assert cashier.status_code == 200, cashier.text
    denied = client.post(
        f"/api/v1/categories/{source_id}/move-and-delete",
        headers={**device(), **bearer(cashier.json()["access_token"])},
        json={"destination_category_id": destination_id},
    )
    assert denied.status_code == 403
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "manager.move",
            "email": "manager.move@example.com",
            "full_name": "Branch Manager",
            "role_id": STORE_MANAGER_ROLE,
            "store_id": DT,
            "password": "manager-password-1",
            "has_portal_access": True,
        },
    )
    assert created.status_code == 201, created.text
    token = client.post(
        "/api/v1/auth/login-password", json={"username": "manager.move", "password": "manager-password-1"}
    ).json()["access_token"]
    scoped = client.delete(f"/api/v1/categories/{source_id}", headers=bearer(token))
    assert scoped.status_code == 403
    assert scoped.json()["error"]["code"] == "store_scope"
