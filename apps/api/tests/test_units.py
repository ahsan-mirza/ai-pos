from wholesale_support import CABLE, PHONE, admin, device, event, line, push, sale, seed


def create_case(client, headers: dict[str, str], **overrides) -> dict:
    body = {"code": "case 24", "name": "Case of 24", "short_name": "Case", "factor": 24, **overrides}
    response = client.post("/api/v1/units", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def sell_cable_in(client, headers: dict[str, str], units: list[str]) -> None:
    response = client.put(f"/api/v1/pricing/products/{CABLE}", headers=headers, json={"sellable_units": units})
    assert response.status_code == 200, response.text


def test_built_in_units_are_listed_and_custom_units_are_created(client) -> None:
    seed(client)
    headers, _ = admin(client)
    case = create_case(client, headers)
    assert case["code"] == "CASE_24" and case["factor"] == 24 and case["is_system"] is False
    listed = client.get("/api/v1/units", headers=device()).json()
    assert [(row["code"], row["factor"]) for row in listed] == [
        ("PIECE", 1),
        ("BOX_10", 10),
        ("CASE_24", 24),
        ("CARTON_100", 100),
    ]
    assert client.post("/api/v1/units", headers=headers, json={**case, "id": None}).status_code == 422
    duplicate = client.post(
        "/api/v1/units", headers=headers, json={"code": "CASE_24", "name": "Again", "short_name": "C", "factor": 24}
    )
    assert duplicate.status_code == 409
    built_in = client.post(
        "/api/v1/units", headers=headers, json={"code": "BOX_10", "name": "Box", "short_name": "Box", "factor": 12}
    )
    assert built_in.status_code == 409
    assert client.post("/api/v1/units", headers=device(), json={**case, "code": "PACK_6"}).status_code == 403


def test_products_sell_in_custom_packs_and_carry_their_factors(client) -> None:
    seed(client)
    headers, _ = admin(client)
    create_case(client, headers)
    sell_cable_in(client, headers, ["CASE_24"])
    product = client.get(f"/api/v1/products/{CABLE}", headers=device()).json()
    assert product["sellable_units"] == ["PIECE", "CASE_24"]
    assert [(row["code"], row["short_name"], row["factor"]) for row in product["unit_options"]] == [
        ("PIECE", "Pcs", 1),
        ("CASE_24", "Case", 24),
    ]

    body = sale([line(CABLE, 48, 1000, unit_type="CASE_24")])
    assert push(client, [event("uom-two-cases", "sale", body)]).status_code == 200
    stored = client.get(f"/api/v1/sales/{body['id']}", headers=device()).json()
    assert stored["items"][0]["unit_type"] == "CASE_24" and stored["items"][0]["quantity"] == 48

    broken = push(client, [event("uom-part-case", "sale", sale([line(CABLE, 30, 1000, unit_type="CASE_24")]))])
    assert broken.status_code == 422 and "whole number of Case of 24" in broken.json()["error"]["message"]
    unknown = push(client, [event("uom-unknown", "sale", sale([line(CABLE, 12, 1000, unit_type="DOZEN")]))])
    assert unknown.status_code == 422
    not_listed = push(client, [event("uom-box-10", "sale", sale([line(CABLE, 10, 1000, unit_type="BOX_10")]))])
    assert not_listed.status_code == 422 and "box of 10" in not_listed.json()["error"]["message"]


def test_pack_rules_for_serialized_unknown_and_retired_units(client) -> None:
    seed(client, phone_units=1)
    headers, _ = admin(client)
    case = create_case(client, headers)
    serialized = client.put(f"/api/v1/pricing/products/{PHONE}", headers=headers, json={"sellable_units": ["CASE_24"]})
    assert serialized.status_code == 422
    unknown = client.put(f"/api/v1/pricing/products/{CABLE}", headers=headers, json={"sellable_units": ["DOZEN"]})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "unknown_unit"

    sell_cable_in(client, headers, ["CASE_24"])
    in_use = client.patch(f"/api/v1/units/{case['id']}", headers=headers, json={"is_active": False})
    assert in_use.status_code == 409 and in_use.json()["error"]["code"] == "unit_in_use"
    assert client.delete(f"/api/v1/units/{case['id']}", headers=headers).status_code == 409

    one_case = sale([line(CABLE, 24, 1000, unit_type="CASE_24")])
    assert push(client, [event("uom-sold-case", "sale", one_case)]).status_code == 200
    sell_cable_in(client, headers, ["PIECE"])
    sold_before = client.delete(f"/api/v1/units/{case['id']}", headers=headers)
    assert sold_before.status_code == 409 and "switch it off" in sold_before.json()["error"]["message"]
    retired = client.patch(
        f"/api/v1/units/{case['id']}", headers=headers, json={"is_active": False, "name": "Case (old)"}
    )
    assert retired.status_code == 200 and retired.json()["is_active"] is False
    reassigned = client.put(f"/api/v1/pricing/products/{CABLE}", headers=headers, json={"sellable_units": ["CASE_24"]})
    assert reassigned.status_code == 422 and reassigned.json()["error"]["code"] == "inactive_unit"

    unused = create_case(client, headers, code="PACK_6", name="Six pack", short_name="6pk", factor=6)
    assert client.delete(f"/api/v1/units/{unused['id']}", headers=headers).status_code == 204


def test_product_form_sets_packs_and_weighed_goods_stay_in_grams(client) -> None:
    seed(client)
    headers, _ = admin(client)
    create_case(client, headers)
    edited = client.patch(f"/api/v1/products/{CABLE}", headers=headers, json={"sellable_units": ["CASE_24"]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["sellable_units"] == ["PIECE", "CASE_24"]
    assert [row["code"] for row in edited.json()["unit_options"]] == ["PIECE", "CASE_24"]
    weighed = client.patch(
        f"/api/v1/products/{CABLE}", headers=headers, json={"sold_by_weight": True, "sellable_units": ["CASE_24"]}
    )
    assert weighed.status_code == 422
