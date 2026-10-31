"""Starter modifier groups for restaurant and café stores. Electronics never receives them."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tests.test_returns import CABLE_ID, admin_token, bearer, seed_catalog

from app.core import capabilities as catalog
from app.models.menu import ModifierGroup
from app.services.menu_service import ensure_default_groups


def _profile(client, token: str, profile: str) -> None:
    chosen = [capability.value for capability in catalog.PROFILES[profile]]
    response = client.put(
        "/api/v1/settings/profile",
        headers=bearer(token),
        json={"business_profile": profile, "capabilities": chosen},
    )
    assert response.status_code == 200, response.text


def test_electronics_does_not_receive_restaurant_modifiers(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    assert ensure_default_groups(session) == 0
    assert session.scalar(select(func.count()).select_from(ModifierGroup)) == 0
    denied = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    assert denied.status_code == 403


def test_a_restaurant_gets_starter_groups_once_and_keeps_edits(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _profile(client, token, "restaurant")

    first = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    assert first.status_code == 200, first.text
    groups = {row["name"]: row for row in first.json()}
    assert set(groups) == {"Size", "Add-ons", "Spice level", "Sauces"}
    assert "Milk" not in groups
    size = groups["Size"]
    assert size["min_select"] == 0 and size["max_select"] == 1
    assert [option["name"] for option in size["options"]] == ["Regular", "Medium", "Large"]
    assert all(option["price_delta_cents"] == 0 for option in size["options"])
    assert size["product_ids"] == []
    assert groups["Add-ons"]["max_select"] == 5

    again = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    assert [row["id"] for row in again.json()] == [row["id"] for row in first.json()]

    renamed = client.put(
        f"/api/v1/menu/modifier-groups/{size['id']}",
        headers=bearer(token),
        json={
            "name": "Cup size",
            "min_select": 0,
            "max_select": 1,
            "options": [
                {"id": size["options"][0]["id"], "name": "Regular", "price_delta_cents": 0},
                {"id": size["options"][1]["id"], "name": "Medium", "price_delta_cents": 200},
                {"id": size["options"][2]["id"], "name": "Large", "price_delta_cents": 0},
            ],
        },
    )
    assert renamed.status_code == 200, renamed.text
    linked = client.put(
        f"/api/v1/menu/products/{CABLE_ID}/modifier-groups",
        headers=bearer(token),
        json={"group_ids": [groups["Sauces"]["id"]]},
    )
    assert linked.status_code == 200, linked.text

    kept = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    names = [row["name"] for row in kept.json()]
    assert names.count("Cup size") == 1
    assert "Size" not in names
    cup = next(row for row in kept.json() if row["name"] == "Cup size")
    assert cup["options"][1]["price_delta_cents"] == 200
    sauces = next(row for row in kept.json() if row["name"] == "Sauces")
    assert sauces["product_ids"] == [CABLE_ID]

    blocked = client.delete(f"/api/v1/menu/modifier-groups/{sauces['id']}", headers=bearer(token))
    assert blocked.status_code == 409
    removed = client.delete(f"/api/v1/menu/modifier-groups/{sauces['id']}?detach=true", headers=bearer(token))
    assert removed.status_code == 204
    for row in kept.json():
        if row["id"] == sauces["id"]:
            continue
        gone = client.delete(f"/api/v1/menu/modifier-groups/{row['id']}", headers=bearer(token))
        assert gone.status_code == 204, gone.text

    empty = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    assert empty.json() == []
    restored = client.post("/api/v1/menu/modifier-groups/from-template", headers=bearer(token), json={"key": "size"})
    assert restored.status_code == 201, restored.text
    assert restored.json()["name"] == "Size"
    assert session.scalar(select(func.count()).select_from(ModifierGroup)) == 1


def test_a_cafe_also_receives_milk(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    _profile(client, token, "cafe")
    listed = client.get("/api/v1/menu/modifier-groups", headers=bearer(token))
    assert listed.status_code == 200, listed.text
    names = {row["name"] for row in listed.json()}
    assert names == {"Size", "Add-ons", "Spice level", "Sauces", "Milk"}
    milk = next(row for row in listed.json() if row["name"] == "Milk")
    assert [option["name"] for option in milk["options"]] == [
        "Whole milk",
        "Skimmed milk",
        "Oat milk",
        "Almond milk",
        "Soy milk",
    ]
    copied = client.post(f"/api/v1/menu/modifier-groups/{milk['id']}/duplicate", headers=bearer(token))
    assert copied.status_code == 201, copied.text
    assert copied.json()["name"] == "Milk copy"
    assert copied.json()["product_ids"] == []
    duplicate = client.post("/api/v1/menu/modifier-groups/from-template", headers=bearer(token), json={"key": "milk"})
    assert duplicate.status_code == 409
    assert uuid.UUID(copied.json()["id"])
