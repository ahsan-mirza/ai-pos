"""Personalized vouchers use the promotion engine. They do not touch the credit ledger or loyalty points."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from tests.test_capabilities import change_profile
from tests.test_promotions import discounted, promotion

from app.models.customer import Customer, CustomerCoupon, CustomerLedgerEntry
from app.models.loyalty import LoyaltyEntry
from app.models.promotion import PromotionRedemption
from app.models.sale import Sale
from app.services import coupon_service
from wholesale_support import CABLE, admin, create_customer, event, line, push, sale, seed

PROFILES = ("restaurant", "cafe", "grocery", "retail_fashion", "electronics_wholesale")


def _voucher(session, promotion_id: str, customer_id: str, code: str) -> None:
    session.add(
        CustomerCoupon(
            promotion_id=uuid.UUID(promotion_id),
            customer_id=uuid.UUID(customer_id),
            code=code,
            status="issued",
            reason="Test",
            issued_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(days=7),
            idempotency_key=f"{promotion_id}:{customer_id}:test",
        )
    )
    session.commit()


def _redeem(client, customer_id: str, promotion_id: str, code: str, *, sale_type: str = "RETAIL"):
    item = discounted(CABLE, 1, 1500, 200, promotion_id)
    body = sale(
        [item],
        customer_id=customer_id,
        coupon_code=code,
        sale_type=sale_type,
        tenders=[{"method": "cash", "amount_cents": item["line_total_cents"]}],
    )
    return push(client, [event(str(uuid.uuid4()), "sale", body)]), body


def test_a_voucher_only_redeems_for_its_customer(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    owner = create_customer(client, headers, name="Owner")
    other = create_customer(client, headers, name="Other", trn_vat_number="100200300400004")
    promo = promotion(
        client,
        headers,
        name="Five dirhams",
        kind="AMOUNT_OFF",
        amount_cents=200,
        customer_issued=True,
        segment="loyalty",
        product_ids=[CABLE],
    )
    _voucher(session, promo["id"], owner["id"], "OWNER200")

    wrong = _redeem(client, other["id"], promo["id"], "OWNER200")[0]
    assert wrong.status_code == 422
    assert session.query(CustomerCoupon).one().status == "issued"

    missing = _redeem(client, owner["id"], promo["id"], "OWNER200")
    # The first call above used the owner path only after the rejection. Redeem once for the owner.
    assert missing[0].status_code == 200, missing[0].text
    session.expire_all()
    assert session.query(CustomerCoupon).one().status == "redeemed"
    again = _redeem(client, owner["id"], promo["id"], "OWNER200")[0]
    assert again.status_code == 422
    assert session.query(PromotionRedemption).count() == 1
    assert session.query(CustomerLedgerEntry).count() == 0
    assert session.query(LoyaltyEntry).count() == 0
    report = client.get("/api/v1/promotions/coupon-report", headers=headers)
    assert report.status_code == 200, report.text
    assert report.json()["issued"] == 1
    assert report.json()["redeemed"] == 1
    assert report.json()["discount_cents"] == 200
    assert report.json()["sales"] == 1

    stranger = sale(
        [discounted(CABLE, 1, 1500, 200, promo["id"])],
        coupon_code="OWNER200",
        tenders=[{"method": "cash", "amount_cents": 1300}],
    )
    # Already redeemed, and this sale has no customer. Either rejection leaves no second redemption.
    refused = push(client, [event("no-customer", "sale", stranger)])
    assert refused.status_code == 422
    assert session.query(PromotionRedemption).count() == 1


@pytest.mark.parametrize("profile", PROFILES)
def test_every_profile_redeems_a_voucher_on_the_sale_path(client, session, profile: str) -> None:
    seed(client)
    headers, _ = admin(client)
    if profile != "electronics_wholesale":
        assert change_profile(client, headers, profile).status_code == 200
    customer = create_customer(
        client, headers, name=profile, customer_type="RETAIL", credit_limit_cents=0, payment_terms="DUE_ON_RECEIPT"
    )
    promo = promotion(
        client, headers, kind="AMOUNT_OFF", amount_cents=200, customer_issued=True, segment="milestone", product_ids=[]
    )
    code = profile[:6].upper() + "200"
    _voucher(session, promo["id"], customer["id"], code)
    response, _ = _redeem(client, customer["id"], promo["id"], code, sale_type="WHOLESALE")
    assert response.status_code == 200, response.text
    session.expire_all()
    assert session.query(CustomerCoupon).one().status == "redeemed"
    assert session.query(CustomerLedgerEntry).count() == 0


def test_the_same_period_issues_one_voucher_and_win_back_waits(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    quiet = create_customer(client, headers, name="Quiet")
    recent = create_customer(client, headers, name="Recent", trn_vat_number="100200300400005")
    promotion(
        client,
        headers,
        name="Come back",
        kind="AMOUNT_OFF",
        amount_cents=500,
        customer_issued=True,
        segment="win_back",
        quiet_days=30,
        notify=True,
        product_ids=[],
    )
    old = sale([line(CABLE, 1, 1500)], customer_id=quiet["id"], tenders=[{"method": "cash", "amount_cents": 1500}])
    new = sale([line(CABLE, 1, 1500)], customer_id=recent["id"], tenders=[{"method": "cash", "amount_cents": 1500}])
    assert push(client, [event("old-sale", "sale", old), event("new-sale", "sale", new)]).status_code == 200
    row = session.get(Sale, uuid.UUID(old["id"]))
    row.created_at = datetime.now(UTC) - timedelta(days=40)
    person = session.get(Customer, uuid.UUID(quiet["id"]))
    person.email = "quiet@example.com"
    person.marketing_email_opt_in = True
    from app.models.business_settings import BusinessSettings

    settings_row = session.query(BusinessSettings).one()
    settings_row.capabilities = list(dict.fromkeys([*(settings_row.capabilities or []), "axiz_reach"]))
    session.commit()

    assert coupon_service.issue_due(session) == 1
    assert coupon_service.issue_due(session) == 0
    issued = session.query(CustomerCoupon).one()
    assert issued.customer_id == uuid.UUID(quiet["id"])
    from app.models.messaging import OutboundMessage

    sent = session.query(OutboundMessage).filter_by(template_key="coupon_issued").one()
    assert sent.customer_id == person.id
    assert session.query(CustomerLedgerEntry).count() == 0


def test_a_partial_refund_lowers_net_spend(client, session) -> None:
    seed(client)
    headers, user_id = admin(client)
    customer = create_customer(client, headers, name="Spender")
    promotion(
        client,
        headers,
        name="Big basket",
        kind="PERCENT_OFF",
        percent_bps=1000,
        customer_issued=True,
        segment="basket",
        min_spend_cents=2000,
        product_ids=[],
    )
    body = sale([line(CABLE, 2, 1500)], customer_id=customer["id"], tenders=[{"method": "cash", "amount_cents": 3000}])
    assert push(client, [event("basket-sale", "sale", body)]).status_code == 200
    assert coupon_service.issue_due(session) == 1
    session.query(CustomerCoupon).delete()
    session.commit()

    from wholesale_support import CASHIER_ID, STORE

    payload = {
        "id": str(uuid.uuid4()),
        "original_sale_id": body["id"],
        "store_id": STORE,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "processed_at": datetime.now(UTC).isoformat(),
        "subtotal_cents": 1500,
        "tax_refund_cents": 0,
        "restocking_fee_cents": 0,
        "total_refund_cents": 1500,
        "reason_notes": "One back.",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "sale_item_id": body["items"][0]["id"],
                "product_id": CABLE,
                "quantity": 1,
                "unit_price_cents": 1500,
                "tax_refund_cents": 0,
                "restocking_fee_cents": 0,
                "refund_cents": 1500,
                "condition_status": "unopened_resealable",
                "reason_code": "changed_mind",
            }
        ],
        "tenders": [{"method": "cash", "amount_cents": 1500}],
        "override": {"approved_by_id": user_id, "reasons": ["no_refund_permission"], "note": "Checked."},
    }
    assert push(client, [event("basket-return", "sale_return", payload)]).status_code == 200
    assert coupon_service.issue_due(session) == 0
