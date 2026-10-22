"""List endpoints page with `offset` (or `skip`) + `limit` and report the full match count in X-Total-Count."""

from app.core.pagination import TOTAL_COUNT_HEADER
from test_inventory import CABLE, DT, SHJ, WH, admin, seed
from wholesale_support import create_customer


def page(client, path: str, headers: dict[str, str], **params):
    response = client.get(path, headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json(), int(response.headers[TOTAL_COUNT_HEADER])


def test_customers_page_by_offset_and_skip(client) -> None:
    headers = admin(client)
    for index in range(5):
        create_customer(
            client, headers, name=f"Trader {index}", company_name=f"Trader {index} LLC", phone=f"+9715000{index}"
        )

    first, total = page(client, "/api/v1/customers", headers, limit=2)
    assert total == 5
    assert [row["name"] for row in first] == ["Trader 0", "Trader 1"]

    by_offset, _ = page(client, "/api/v1/customers", headers, limit=2, offset=4)
    by_skip, _ = page(client, "/api/v1/customers", headers, limit=2, skip=4)
    assert [row["name"] for row in by_offset] == [row["name"] for row in by_skip] == ["Trader 4"]

    filtered, filtered_total = page(client, "/api/v1/customers", headers, limit=1, q="trader 3")
    assert filtered_total == 1 and filtered[0]["name"] == "Trader 3"


def test_purchase_orders_and_transfers_report_totals(client) -> None:
    headers = admin(client)
    seed(client)
    for index in range(3):
        created = client.post(
            "/api/v1/inventory/purchase-orders",
            headers=headers,
            json={
                "supplier_name": f"Supplier {index}",
                "destination_store_id": WH,
                "lines": [{"product_id": CABLE, "quantity_ordered": 5, "unit_cost_cents": 600}],
            },
        )
        assert created.status_code == 201, created.text
        moved = client.post(
            "/api/v1/inventory/transfers",
            headers=headers,
            json={"source_store_id": DT, "destination_store_id": SHJ, "lines": [{"product_id": CABLE, "quantity": 1}]},
        )
        assert moved.status_code == 201, moved.text

    orders, order_total = page(client, "/api/v1/inventory/purchase-orders", headers, limit=2)
    rest, _ = page(client, "/api/v1/inventory/purchase-orders", headers, limit=2, offset=2)
    assert order_total == 3 and len(orders) == 2 and len(rest) == 1
    assert {row["id"] for row in orders}.isdisjoint({row["id"] for row in rest})

    transfers, transfer_total = page(client, "/api/v1/inventory/transfers", headers, limit=1, skip=1)
    assert transfer_total == 3 and len(transfers) == 1

    _, none_total = page(client, "/api/v1/inventory/purchase-orders", headers, status="received")
    assert none_total == 0


def test_quotes_batches_and_audit_expose_totals(client) -> None:
    headers = admin(client)
    body, total = page(client, "/api/v1/quotes", headers, limit=10)
    assert total == body["total"] == 0

    batches, batch_total = page(client, "/api/v1/inventory/batches", headers, limit=10)
    assert batch_total == batches["total"]

    logs, log_total = page(client, "/api/v1/audit-logs", headers, limit=1, skip=0)
    assert log_total == logs["total"] >= 1


def test_browsers_can_read_the_total_header(client) -> None:
    response = client.get(
        "/api/v1/customers", headers={**admin(client), "Origin": "http://localhost:5173"}, params={"limit": 1}
    )
    assert TOTAL_COUNT_HEADER.lower() in response.headers["access-control-expose-headers"].lower()


def test_offset_must_not_be_negative(client) -> None:
    response = client.get("/api/v1/customers", headers=admin(client), params={"skip": -1})
    assert response.status_code == 422
