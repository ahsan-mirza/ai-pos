"""Repair job search stays on the server: filters apply before the page, and a receipt is not required to list them."""

from tests.test_warranty import repair

from wholesale_support import admin, device, event, imeis, push, seed


def _book(client, identifier: str, **extra) -> dict:
    ticket = repair(identifier, **extra)
    assert push(client, [event(f"job-{ticket['id'][:8]}", "repair_ticket", ticket)]).status_code == 200
    return ticket


def test_search_and_filters_apply_across_pages(client) -> None:
    seed(client)
    first, second = imeis(2, "35391805313")
    sara = _book(client, first, customer_name="Sara Phone")
    _book(client, second, customer_name="Omar Tablet", device_model="Tablet 11", status="ready")
    headers, _ = admin(client)

    page = client.get("/api/v1/repairs", headers=headers, params={"q": "sara", "limit": 1, "offset": 0})
    assert page.status_code == 200, page.text
    assert page.headers["X-Total-Count"] == "1"
    assert page.json()[0]["id"] == sara["id"]
    assert page.json()[0]["reference"] == sara["id"][:8].upper()
    assert page.json()[0]["parts_cents"] == 0

    ready = client.get("/api/v1/repairs", headers=headers, params={"status": "ready", "ownership": "customer"})
    assert ready.status_code == 200, ready.text
    assert ready.headers["X-Total-Count"] == "1"
    assert ready.json()[0]["device_model"] == "Tablet 11"

    both = client.get("/api/v1/repairs", headers=headers, params={"limit": 1, "offset": 0})
    assert both.headers["X-Total-Count"] == "2"
    second_page = client.get("/api/v1/repairs", headers=headers, params={"limit": 1, "offset": 1})
    assert {both.json()[0]["id"], second_page.json()[0]["id"]} == {sara["id"], ready.json()[0]["id"]}

    refused = client.get("/api/v1/repairs", headers=headers, params={"status": "quality_check"})
    assert refused.status_code == 422

    phone = client.get("/api/v1/repairs", headers=headers, params={"q": "0501234567"})
    assert phone.headers["X-Total-Count"] == "2"


def test_duplicate_match_does_not_block_a_repeat_booking(client) -> None:
    seed(client)
    identifier = imeis(1, "35391805313")[0]
    booked = _book(client, identifier)
    headers, _ = admin(client)
    matches = client.get(
        "/api/v1/repairs/matches",
        headers=headers,
        params={"identifier": identifier, "phone": "050 123 4567"},
    )
    assert matches.status_code == 200, matches.text
    assert matches.json()[0]["id"] == booked["id"]
    again = _book(client, imeis(1, "35391805314")[0], customer_name="Sara Phone")
    assert again["id"] != booked["id"]


def test_register_list_hides_internal_cost(client) -> None:
    seed(client)
    _book(client, imeis(1, "35391805313")[0])
    listed = client.get("/api/v1/repairs", headers=device())
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["parts_cents"] is None
    assert listed.json()[0]["labour_cents"] is None


def test_status_filter_follows_a_persisted_update(client) -> None:
    seed(client)
    ticket = _book(client, imeis(1, "35391805313")[0])
    headers, _ = admin(client)
    moved = client.post(
        f"/api/v1/repairs/{ticket['id']}/status",
        headers=headers,
        json={"status": "diagnosing", "note": "Opened"},
    )
    assert moved.status_code == 200, moved.text
    found = client.get("/api/v1/repairs", headers=headers, params={"status": "diagnosing"})
    assert found.headers["X-Total-Count"] == "1"
    assert found.json()[0]["status"] == "diagnosing"
