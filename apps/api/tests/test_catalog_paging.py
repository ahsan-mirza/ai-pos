"""Registers sync the whole catalog page by page, and search reads the generated search_text column."""

from test_auth import admin_token
from test_product_search import STORE_ID, event, headers, product, search

NAMES = ["Apple", "Apple", "Apple", "Banana", "Cherry"] + [f"Item {index:02d}" for index in range(18)]


def push(client, events: list[dict]) -> None:
    response = client.post("/api/v1/sync/push", headers=headers(), json={"device_id": "paging", "events": events})
    assert response.status_code == 200, response.text
    assert all(result["status"] == "applied" for result in response.json()["results"]), response.text


def seed(client) -> list[str]:
    ids = [f"00000000-0000-4000-8000-{index + 100:012d}" for index in range(len(NAMES))]
    events = [event("paging-store", "store", {"id": STORE_ID, "code": "DT-01", "name": "Downtown", "currency": "USD"})]
    for index, (product_id, name) in enumerate(zip(ids, NAMES, strict=True)):
        row = product(product_id, f"SKU-{index:03d}", f"2{index:011d}", name, "Grocery")
        events.append(event(f"paging-{index}", "product", row))
    push(client, events)
    return ids


def page(client, after: str | None, limit: int):  # type: ignore[no-untyped-def]
    params: dict[str, str | int] = {"limit": limit}
    if after is not None:
        params["after"] = after
    return client.get("/api/v1/products", headers=headers(), params=params)


def test_keyset_pages_cover_the_catalog_once_in_name_order(client) -> None:
    ids = seed(client)
    seen: list[dict] = []
    after: str | None = None
    while True:
        response = page(client, after, 5)
        assert response.status_code == 200, response.text
        rows = response.json()
        seen.extend(rows)
        if len(rows) < 5:
            break
        after = rows[-1]["id"]
    assert sorted(row["id"] for row in seen) == sorted(ids)
    names = [row["name"] for row in seen]
    assert names == sorted(names)


def test_unknown_cursor_is_rejected(client) -> None:
    seed(client)
    response = page(client, "00000000-0000-4000-8000-999999999999", 5)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "bad_cursor"


def test_search_text_follows_renames(client) -> None:
    ids = seed(client)
    assert [hit["product"]["name"] for hit in search(client, "banana")] == ["Banana"]
    bearer = {"Authorization": f"Bearer {admin_token(client)}"}
    renamed = client.patch(f"/api/v1/products/{ids[3]}", headers=bearer, json={"name": "Plantain"})
    assert renamed.status_code == 200, renamed.text
    assert search(client, "banana") == []
    assert [hit["product"]["name"] for hit in search(client, "PLANT")] == ["Plantain"]


def test_separators_are_optional_in_codes(client) -> None:
    seed(client)
    push(
        client,
        [
            event(
                "paging-coded",
                "product",
                product(
                    "00000000-0000-4000-8000-000000000999",
                    "FRT-APL-1KG",
                    "299999999999",
                    "Gala apples",
                    "Fruit",
                    model_number="GA-1 KG",
                ),
            )
        ],
    )
    for query in ("frtapl1kg", "ga1kg", "FRT-APL", "gala fruit"):
        assert [hit["product"]["name"] for hit in search(client, query)] == ["Gala apples"], query
