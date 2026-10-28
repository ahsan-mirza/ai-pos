"""Fashion catalogue: product photos (tenant-prefixed storage, colour photos, covers), the season / collection /
gender attributes on models and variants, and the sales associate credited for commissions."""

import io
import uuid

import pytest
from PIL import Image
from sqlalchemy.orm import Session
from tests.test_fashion import tee_model
from tests.test_returns import admin_token, bearer, seed_catalog

from app.models import Product, Sale
from app.services import media_storage
from app.tenancy.context import TenantRef, use_tenant
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, event, line, push, sale, seed


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setattr(media_storage, "ROOT", tmp_path)
    return tmp_path


def png(color: str = "black", size: tuple[int, int] = (1600, 900)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, "PNG")
    return buffer.getvalue()


def grid(client, token: str) -> tuple[str, dict[str, dict]]:
    model_id = tee_model(client, token)
    body = {"axes": [{"key": "size", "values": ["S", "M"]}, {"key": "color", "values": ["Black", "White"]}]}
    created = client.post(
        f"/api/v1/product-models/{model_id}/matrix", headers=bearer(token), json={**body, "price_cents": 4900}
    )
    assert created.status_code == 200, created.text
    cells = {f"{c['attributes']['size']}-{c['attributes']['color']}": c for c in created.json()["cells"]}
    return model_id, cells


def product(client, token: str, product_id: str) -> dict:
    response = client.get(f"/api/v1/products/{product_id}", headers=bearer(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_photos_are_resized_stored_per_tenant_and_cover_each_colour(client, media_root) -> None:
    seed_catalog(client)
    token = admin_token(client)
    model_id, cells = grid(client, token)
    headers = bearer(token)

    general = client.post(
        f"/api/v1/product-models/{model_id}/images",
        headers=headers,
        files={"file": ("tee.png", png("gray"), "image/png")},
    )
    assert general.status_code == 201, general.text
    assert general.json()["is_primary"] and (general.json()["width"], general.json()["height"]) == (1200, 675)
    black = client.post(
        f"/api/v1/product-models/{model_id}/images",
        headers=headers,
        files={"file": ("black.png", png("black"), "image/png")},
        data={"attribute_value": "Black"},
    )
    assert black.status_code == 201 and black.json()["attribute_key"] == "color"

    assert product(client, token, cells["M-Black"]["product_id"])["image_url"] == black.json()["url"]
    assert product(client, token, cells["M-White"]["product_id"])["image_url"] == general.json()["url"]
    own = client.post(
        f"/api/v1/inventory/products/{cells['S-White']['product_id']}/images",
        headers=headers,
        files={"file": ("white.png", png("white", (400, 400)), "image/png")},
    )
    assert own.status_code == 201
    assert product(client, token, cells["S-White"]["product_id"])["thumb_url"] == own.json()["thumb_url"]

    key = black.json()["url"].split("/media/", 1)[1]
    assert key.startswith("default/products/")
    assert (media_root / "default" / "media" / key.split("/", 1)[1]).is_file()
    served = client.get(f"/media/{key}")
    assert served.status_code == 200 and served.headers["content-type"] == "image/webp"
    assert "immutable" in served.headers["cache-control"]
    assert client.get("/media/other-store/" + key.split("/", 1)[1]).status_code == 404
    assert client.get("/media/default/products/..%2F..%2Fsecret.webp").status_code == 404

    deleted = client.delete(f"/api/v1/inventory/images/{general.json()['id']}", headers=headers)
    assert deleted.status_code == 204
    remaining = client.get(f"/api/v1/product-models/{model_id}/images", headers=headers).json()
    assert [row["id"] for row in remaining] == [black.json()["id"]] and remaining[0]["is_primary"]
    assert client.get("/media/" + general.json()["url"].split("/media/", 1)[1]).status_code == 404


def test_photos_saved_without_a_store_are_copied_into_that_store(media_root) -> None:
    key = "products/" + ("ab" * 16) + ".webp"
    media_storage.storage_for("default").put(key, b"webp-bytes")
    ref = TenantRef(id="00000000-0000-4000-8000-0000000000a1", slug="alpha", name="Alpha", database_url="sqlite://")
    with use_tenant(ref):
        served = media_storage.url(key)
    assert served.endswith(f"/media/alpha/{key}")
    assert (media_root / "alpha" / "media" / "products" / f"{'ab' * 16}.webp").is_file()
    assert (media_root / "default" / "media" / "products" / f"{'ab' * 16}.webp").is_file()


def test_only_photos_are_accepted(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    model_id = tee_model(client, token)
    headers = bearer(token)
    text = client.post(
        f"/api/v1/product-models/{model_id}/images", headers=headers, files={"file": ("a.txt", b"hello", "text/plain")}
    )
    assert text.status_code == 415
    fake = client.post(
        f"/api/v1/product-models/{model_id}/images",
        headers=headers,
        files={"file": ("a.png", b"not a png", "image/png")},
    )
    assert fake.status_code == 415 and "not a JPEG" in fake.text
    assert (
        client.post(
            f"/api/v1/product-models/{uuid.uuid4()}/images",
            headers=headers,
            files={"file": ("a.png", png(), "image/png")},
        ).status_code
        == 404
    )


def test_model_attributes_flow_to_variants_search_and_filters(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    model_id, cells = grid(client, token)
    headers = bearer(token)
    updated = client.patch(
        f"/api/v1/product-models/{model_id}",
        headers=headers,
        json={"season": " ss26 ", "collection": "Resort  Edit", "gender": "Women", "material": "Organic cotton"},
    )
    assert updated.status_code == 200, updated.text
    assert (updated.json()["season"], updated.json()["collection"], updated.json()["gender"]) == (
        "SS26",
        "Resort Edit",
        "women",
    )
    variant = product(client, token, cells["M-Black"]["product_id"])
    assert (variant["season"], variant["material"]) == ("SS26", "Organic cotton")

    filtered = client.get("/api/v1/products?season=ss26&gender=women", headers=headers).json()
    assert {row["id"] for row in filtered} == {cell["product_id"] for cell in cells.values()}
    assert client.get("/api/v1/products?season=AW25", headers=headers).json() == []
    found = client.get("/api/v1/products/search?q=resort", headers=headers).json()
    assert {hit["product"]["id"] for hit in found} >= {cells["S-White"]["product_id"]}

    picker = client.get("/api/v1/catalog/attributes", headers=headers).json()
    assert picker["seasons"] == ["SS26"] and picker["genders"] == ["women"]
    assert picker["materials"] == ["Organic cotton"]
    cleared = client.patch(f"/api/v1/product-models/{model_id}", headers=headers, json={"season": None})
    assert cleared.json()["season"] is None
    session.expire_all()
    assert session.get(Product, uuid.UUID(cells["S-Black"]["product_id"])).season is None
    assert session.get(Product, uuid.UUID(cells["S-Black"]["product_id"])).collection == "Resort Edit"


def test_sales_associate_is_recorded_and_earns_the_commission(client, session: Session) -> None:
    seed(client)
    headers, _ = admin(client)
    roles = {row["name"]: row["id"] for row in client.get("/api/v1/roles", headers=headers).json()}
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "stylist",
            "email": "stylist@example.com",
            "full_name": "Sara Stylist",
            "role_id": roles["Cashier"],
            "password": "stylist-pass-123",
            "pin": "246810",
            "has_portal_access": False,
            "has_pos_access": True,
            "store_id": STORE,
        },
    )
    assert created.status_code == 201, created.text
    stylist_id = created.json()["id"]

    body = sale([line(CABLE, 2, 1500)])
    body["sales_associate_id"] = stylist_id
    result = push(client, [event("fashion-assoc-1", "sale", body)])
    assert result.json()["results"][0]["status"] == "applied", result.text
    recorded = session.get(Sale, uuid.UUID(body["id"]))
    assert str(recorded.sales_associate_id) == stylist_id and str(recorded.cashier_id) == CASHIER_ID

    stranger = sale([line(CABLE, 1, 1500)])
    stranger["sales_associate_id"] = str(uuid.uuid4())
    rejected = push(client, [event("fashion-assoc-2", "sale", stranger)])
    assert "sales associate does not exist" in rejected.text

    # wholesale_support stamps every sync event 2026-10-19, which becomes the sale date.
    report = client.get("/api/v1/reports/management/staff?from=2026-10-01&to=2026-10-31", headers=headers)
    assert report.status_code == 200, report.text
    rows = {row["user_id"]: row for row in report.json()["rows"]}
    assert stylist_id in rows and rows[stylist_id]["units"] == 2
