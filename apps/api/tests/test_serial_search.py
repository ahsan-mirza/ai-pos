import uuid

from app.models.serial_number import SerialNumber
from wholesale_support import PHONE, STORE, admin, device, push, seed


def _token(client, username: str, pin: str) -> dict[str, str]:
    body = client.post("/api/v1/auth/login-pin", json={"username": username, "pin": pin}, headers=device()).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def test_register_lists_and_filters_in_stock_units(client) -> None:
    values = seed(client, phone_units=3)
    in_stock = client.get("/api/v1/serials/search", headers=device(), params={"product_id": PHONE, "store_id": STORE})
    assert in_stock.status_code == 200, in_stock.text
    body = in_stock.json()
    assert body["match"] == "all" and sorted(row["value"] for row in body["rows"]) == sorted(values)
    assert all(row["purchase_cost_cents"] is None for row in body["rows"])

    exact = client.get("/api/v1/serials/search", headers=device(), params={"query": values[1]}).json()
    assert exact["match"] == "exact" and [row["value"] for row in exact["rows"]] == [values[1]]

    tail = values[2][-5:]
    suffix = client.get("/api/v1/serials/search", headers=device(), params={"query": tail, "product_id": PHONE}).json()
    assert suffix["match"] == "suffix" and values[2] in [row["value"] for row in suffix["rows"]]

    partial = client.get("/api/v1/serials/search", headers=device(), params={"query": values[0][:9]}).json()
    assert partial["rows"] == [] and "last 3" in partial["hint"]
    unusable = client.get("/api/v1/serials/search", headers=device(), params={"query": "a b"}).json()
    assert unusable["match"] == "none" and unusable["hint"]


def test_portal_users_see_masked_values_unless_they_manage_stock(client, session) -> None:
    values = seed(client, phone_units=1)
    headers, _ = admin(client)
    full = client.get("/api/v1/serials/search", headers=headers, params={"query": values[0]}).json()["rows"][0]
    assert full["value"] == values[0] and full["product_name"] == "Pixel 9" and full["store_code"] == "DT-01"

    cashier = _token(client, "cashier", "1357")
    at_register = client.get("/api/v1/serials/search", headers=cashier, params={"query": values[0]}).json()["rows"][0]
    assert at_register["value"] == values[0] and at_register["purchase_cost_cents"] is None

    assert session.get(SerialNumber, uuid.UUID(full["id"])).value_suffix == values[0][-6:]


def test_old_rows_get_their_suffix_backfilled(client, session) -> None:
    values = seed(client, phone_units=2)
    session.query(SerialNumber).update({SerialNumber.value_suffix: None})
    session.commit()
    found = client.get("/api/v1/serials/search", headers=device(), params={"query": values[0][-4:]}).json()
    assert values[0] in [row["value"] for row in found["rows"]]
    session.expire_all()
    assert session.query(SerialNumber).filter(SerialNumber.value_suffix.is_(None)).count() == 0


def test_sold_units_are_found_with_status_any(client) -> None:
    values = seed(client, phone_units=1)
    from wholesale_support import event, line, sale

    order = sale([line(PHONE, 1, 79_900, serial=values[0])])
    assert push(client, [event("serial-search-sale", "sale", order)]).status_code == 200
    gone = client.get("/api/v1/serials/search", headers=device(), params={"query": values[0]}).json()
    assert gone["rows"] == []
    anywhere = client.get(
        "/api/v1/serials/search", headers=device(), params={"query": values[0], "status": "any"}
    ).json()
    assert anywhere["rows"][0]["status"] == "sold"
