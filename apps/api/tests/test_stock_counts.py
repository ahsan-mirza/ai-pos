from tests.test_inventory import CABLE, DT, PHONE, admin, stock
from tests.test_manual_adjustments import IMEIS, adjust, adjustment, portal_user

COUNTS = "/api/v1/inventory/counts"


def row(client, headers, product_id: str, store_id: str) -> dict:
    return next(item for item in stock(client, headers, store_id=store_id)["rows"] if item["product_id"] == product_id)


def counter(client, headers) -> dict[str, str]:
    role = client.post(
        "/api/v1/roles",
        headers=headers,
        json={"name": "Stock Counter", "description": "Counts shelves.", "permissions": ["portal:access"]},
    )
    assert role.status_code == 201, role.text
    return portal_user(client, headers, "counter.dt", role.json()["id"], DT)


def open_count(client, headers, **extra) -> dict:
    created = client.post(COUNTS, headers=headers, json={"store_id": DT, **extra})
    assert created.status_code == 201, created.text
    return created.json()


def line(count: dict, product_id: str) -> dict:
    return next(item for item in count["lines"] if item["product_id"] == product_id)


def test_blind_count_hides_expected_then_posting_books_the_variance(client) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = admin(client)
    count = open_count(client, headers)
    assert count["number"].endswith("-000001") and "CNT" in count["number"]
    staff = counter(client, headers)

    counted = client.put(
        f"{COUNTS}/{count['id']}/lines", headers=staff, json={"entries": [{"product_id": CABLE, "counted_qty": 7}]}
    )
    assert counted.status_code == 200, counted.text
    blind = line(counted.json(), CABLE)
    assert blind["counted_qty"] == 7 and blind["expected_qty"] is None and blind["variance"] is None
    assert counted.json()["can_review"] is False

    assert client.post(f"{COUNTS}/{count['id']}/post", headers=staff).status_code == 403
    assert client.post(f"{COUNTS}/{count['id']}/submit", headers=staff).json()["status"] == "SUBMITTED"
    late = client.put(
        f"{COUNTS}/{count['id']}/lines", headers=staff, json={"entries": [{"product_id": CABLE, "counted_qty": 8}]}
    )
    assert late.status_code == 409

    review = client.get(f"{COUNTS}/{count['id']}", headers=headers).json()
    assert line(review, CABLE)["expected_qty"] == 10 and line(review, CABLE)["variance"] == -3
    assert review["net_variance"] == -3

    posted = client.post(f"{COUNTS}/{count['id']}/post", headers=headers)
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "POSTED"
    assert row(client, headers, CABLE, DT)["quantity_on_hand"] == 7
    ledger = client.get(
        "/api/v1/inventory/movements", headers=headers, params={"product_id": CABLE, "store_id": DT}
    ).json()
    booked = [m for m in ledger if m["reference_type"] == "stock_count"]
    assert [(m["movement_type"], m["quantity"], m["reason_code"]) for m in booked] == [
        ("AUDIT_ADJUSTMENT", -3, "PHYSICAL_COUNT_AUDIT")
    ]


def test_missing_serialized_units_are_quarantined(client) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = admin(client)
    added = adjust(
        client,
        headers,
        adjustment(
            PHONE,
            DT,
            "add",
            2,
            "SUPPLIER_SAMPLE_IN",
            new_serials=[{"kind": "imei", "value": IMEIS[0]}, {"kind": "imei", "value": IMEIS[1]}],
        ),
    )
    assert added.status_code == 201, added.text
    before = row(client, headers, PHONE, DT)["quantity_on_hand"]
    count = open_count(client, headers, blind=False)
    scanned = client.put(
        f"{COUNTS}/{count['id']}/lines",
        headers=headers,
        json={"entries": [{"product_id": PHONE, "serials": [{"kind": "imei", "value": IMEIS[0]}]}]},
    ).json()
    phone = line(scanned, PHONE)
    assert phone["counted_qty"] == 1 and phone["scanned_tails"] == [f"…{IMEIS[0][-4:]}"]
    assert f"…{IMEIS[1][-4:]}" in phone["missing_serials"]

    posted = client.post(f"{COUNTS}/{count['id']}/post", headers=headers).json()
    assert f"…{IMEIS[1][-4:]}" in line(posted, PHONE)["missing_serials"]
    assert row(client, headers, PHONE, DT)["quantity_on_hand"] == before - len(line(posted, PHONE)["missing_serials"])


def test_overlapping_counts_and_measure_rules(client) -> None:
    from tests.test_inventory import seed

    seed(client)
    headers = admin(client)
    count = open_count(client, headers)
    assert client.post(COUNTS, headers=headers, json={"store_id": DT}).status_code == 409
    wrong = client.put(
        f"{COUNTS}/{count['id']}/lines", headers=headers, json={"entries": [{"product_id": PHONE, "counted_qty": 2}]}
    )
    assert wrong.status_code == 422 and "Scan each" in wrong.json()["error"]["message"]
    assert client.post(f"{COUNTS}/{count['id']}/submit", headers=headers).status_code == 422
    assert client.post(f"{COUNTS}/{count['id']}/cancel", headers=headers).json()["status"] == "CANCELLED"
    assert client.post(COUNTS, headers=headers, json={"store_id": DT}).status_code == 201
