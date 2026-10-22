import json
import uuid
from pathlib import Path

import pytest

from app.models.audit_log import AuditLog
from app.models.promotion import PromotionRedemption
from app.services.promotion_engine import Line, Rule, apply_promotions
from wholesale_support import CABLE, admin, event, line, push, sale, seed

FIXTURE = Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "fixtures" / "promotion-cases.json"
CASES = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_engine_matches_the_shared_fixture(case: dict) -> None:
    lines = [Line(**row) for row in case["lines"]]
    rules = [Rule.from_dict(row) for row in case["rules"]]
    awards = [award.__dict__ for award in apply_promotions(lines, rules)]
    assert awards == case["awards"]


def discounted(product_id: str, quantity: int, unit: int, discount: int, promotion_id: str | None) -> dict:
    item = line(product_id, quantity, unit)
    item["line_total_cents"] = unit * quantity - discount
    item["discount_cents"] = discount
    item["promotion_id"] = promotion_id
    return item


def promotion(client, headers, **overrides) -> dict:
    body = {"name": "Cable week", "kind": "PERCENT_OFF", "percent_bps": 1000, "product_ids": [CABLE]}
    body.update(overrides)
    response = client.post("/api/v1/promotions", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_synced_sales_are_checked_against_the_rules(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    promo = promotion(client, headers)
    assert (
        client.get("/api/v1/promotions/active", headers={"X-Api-Key": "test-api-key-value"}).json()[0]["id"]
        == promo["id"]
    )

    fair = sale([discounted(CABLE, 4, 1500, 600, promo["id"])])
    assert push(client, [event("promo-fair", "sale", fair)]).status_code == 200
    greedy = sale([discounted(CABLE, 2, 1500, 900, promo["id"])])
    assert push(client, [event("promo-greedy", "sale", greedy)]).status_code == 200
    flags = session.query(AuditLog).filter(AuditLog.action == "sale.promotion_mismatch").all()
    assert len(flags) == 1 and "claimed 9.00 but the rules allow 3.00" in json.dumps(flags[0].details)

    listed = client.get("/api/v1/promotions", headers=headers).json()[0]
    assert listed["uses_count"] == 2 and listed["discount_given_cents"] == 1500

    unknown = sale([discounted(CABLE, 1, 1500, 150, str(uuid.uuid4()))])
    rejected = push(client, [event("promo-unknown", "sale", unknown)])
    assert rejected.status_code == 422 and "promotion" in rejected.json()["error"]["message"]


def test_coupon_promotions_need_the_code(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    promo = promotion(client, headers, name="Welcome", coupon_code="welcome10", max_uses=5)
    assert promo["coupon_code"] == "WELCOME10"
    duplicate = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={"name": "Copy", "kind": "PERCENT_OFF", "percent_bps": 500, "coupon_code": "WELCOME10"},
    )
    assert duplicate.status_code == 409

    with_code = sale([discounted(CABLE, 1, 1500, 150, promo["id"])], coupon_code="welcome10")
    assert push(client, [event("coupon-ok", "sale", with_code)]).status_code == 200
    without = sale([discounted(CABLE, 1, 1500, 150, promo["id"])])
    assert push(client, [event("coupon-missing", "sale", without)]).status_code == 200
    flags = session.query(AuditLog).filter(AuditLog.action == "sale.promotion_mismatch").all()
    assert len(flags) == 1 and "coupon not entered" in json.dumps(flags[0].details)
    assert session.query(PromotionRedemption).count() == 2


def test_promotion_rules_are_validated(client) -> None:
    seed(client)
    headers, _ = admin(client)
    bad = client.post(
        "/api/v1/promotions", headers=headers, json={"name": "Broken", "kind": "BUY_X_GET_Y", "buy_qty": 2}
    )
    assert bad.status_code == 422
    lone = client.post(
        "/api/v1/promotions",
        headers=headers,
        json={
            "name": "Lone",
            "kind": "BUNDLE",
            "components": [{"product_id": CABLE, "quantity": 1}],
            "bundle_price_cents": 1,
        },
    )
    assert lone.status_code == 422
