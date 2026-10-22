import uuid

from app.models.sale_item import SaleItem
from test_costing import add_batch
from wholesale_support import CABLE, STORE, admin, device, event, line, push, sale, seed


def test_floor_price_flags_and_approves_below_margin_sales(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    add_batch(session, quantity=20, cost=1000)
    policies = client.put("/api/v1/margin/policies", headers=headers, json={"scope": "GLOBAL", "min_margin_bps": 2000})
    assert policies.status_code == 200, policies.text

    floors = client.get("/api/v1/margin/floors", headers=device(), params={"store_id": STORE}).json()
    cable = next(row for row in floors if row["product_id"] == CABLE)
    assert (cable["floor_cents"], cable["cost_cents"]) == (1200, 1000)

    cheap = line(CABLE, 1, 1100, listed=1500, override_by=headers_admin_id(client, headers))
    unapproved = sale([cheap])
    assert push(client, [event("floor-unapproved", "sale", unapproved)]).status_code == 200
    row = session.query(SaleItem).filter(SaleItem.sale_id == uuid.UUID(unapproved["id"])).one()
    assert (row.floor_cents, row.below_floor_approved_by_id) == (1200, None)

    approved_line = {
        **line(CABLE, 1, 1100, listed=1500, override_by=headers_admin_id(client, headers)),
        "below_floor_override": {"approved_by_id": headers_admin_id(client, headers), "note": "Clearance"},
    }
    approved = sale([approved_line])
    assert push(client, [event("floor-approved", "sale", approved)]).status_code == 200

    report = client.get("/api/v1/margin/exceptions", headers=headers).json()
    assert report["total_shortfall_cents"] == 200
    assert {row["approved_by_name"] is None for row in report["exceptions"]} == {True, False}


def headers_admin_id(client, headers) -> str:
    return client.get("/api/v1/auth/me", headers=headers).json()["id"]
