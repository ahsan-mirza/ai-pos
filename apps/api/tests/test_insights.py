import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_batches import cable_batch
from tests.test_returns import CABLE_ID, STORE_ID, admin_token, bearer, record_sale, seed_catalog

from app.core.config import get_settings
from app.core.permissions import CASHIER_ROLE_ID
from app.core.security import hash_pin
from app.models.audit_log import AuditLog
from app.models.batch import BatchItem
from app.models.inventory import StockMovement
from app.models.product import Product
from app.models.sale import Sale
from app.models.shift import RegisterShift
from app.models.store import Store
from app.models.user import User
from app.services import costing, insights_service, management_reports

TEAM = ("Ali", "Bea", "Cem", "Dina", "Eve")


def seed_team(session: Session) -> dict[str, uuid.UUID]:
    """Five cashiers with 20 sales each. Eve voids nine items and comes up short on three drawers."""
    session.add(Store(id=uuid.UUID(STORE_ID), code="DT-01", name="Downtown", currency="USD"))
    settings = get_settings()
    team: dict[str, uuid.UUID] = {}
    for index, name in enumerate(TEAM):
        user = User(
            id=uuid.uuid4(),
            username=name.lower(),
            email=f"{name.lower()}@example.com",
            full_name=name,
            hashed_pin=hash_pin(f"{index + 3}{index + 3}{index + 3}{index + 3}", settings),
            is_active=True,
            store_id=None,
            role_id=uuid.UUID(CASHIER_ROLE_ID),
            has_pos_access=True,
            has_portal_access=False,
            failed_login_attempts=0,
            token_version=0,
        )
        session.add(user)
        team[name] = user.id
    session.flush()
    for name, user_id in team.items():
        for _ in range(20):
            session.add(
                Sale(
                    store_id=uuid.UUID(STORE_ID),
                    cashier_id=user_id,
                    status="completed",
                    currency="USD",
                    payment_method="cash",
                    subtotal_cents=1000,
                    tax_cents=0,
                    total_cents=1000,
                    amount_paid_cents=1000,
                    due_balance_cents=0,
                    client_sale_id=str(uuid.uuid4()),
                )
            )
        voids = {"Ali": 1, "Cem": 1, "Eve": 9}.get(name, 0)
        for _ in range(voids):
            session.add(
                AuditLog(
                    user_id=user_id,
                    store_id=uuid.UUID(STORE_ID),
                    action_type="ITEM_VOID",
                    action="register.item_void",
                    target_entity="Sale",
                    client_device="desktop",
                    details={},
                )
            )
    now = datetime.now(UTC)
    for day in range(3):
        session.add(
            RegisterShift(
                id=uuid.uuid4(),
                store_id=uuid.UUID(STORE_ID),
                opened_by_id=team["Eve"],
                opened_at=now - timedelta(days=day + 1, hours=8),
                closed_at=now - timedelta(days=day + 1),
                currency="USD",
                status="CLOSED",
                opening_float_cents=10_000,
                counted_cash_cents=7_500,
                expected_cash_cents=10_000,
                variance_cents=-2_500,
                notes="",
            )
        )
    session.commit()
    return team


def test_a_quiet_team_does_not_flag_one_extra_event() -> None:
    median, score = insights_service.robust_score(2.0, [0.0, 0.0, 0.0, 0.0])
    assert median == 0 and score < insights_service.MEDIUM_SCORE
    _, outlier = insights_service.robust_score(45.0, [5.0, 0.0, 5.0, 0.0])
    assert outlier >= insights_service.HIGH_SCORE


def test_anomalies_flag_the_outlier_cashier_and_short_drawers(client, session: Session) -> None:
    team = seed_team(session)
    report = insights_service.detect_anomalies(session, days=30, scope=None)
    assert report.peers == 5
    flagged = {(item.user_name, item.kind): item for item in report.anomalies}
    assert set(flagged) == {("Eve", "VOIDS"), ("Eve", "CASH_SHORT")}
    voids = flagged[("Eve", "VOIDS")]
    assert voids.severity == "HIGH" and voids.count == 9 and voids.rate == 45.0
    assert "team median" in voids.summary
    short = flagged[("Eve", "CASH_SHORT")]
    assert short.severity == "MEDIUM" and short.amount_cents == 7_500 and short.count == 3
    eve = next(row for row in report.staff if row.user_id == team["Eve"])
    assert eve.sales == 20 and eve.voids == 9 and eve.cash_short_cents == 7_500

    headers = bearer(admin_token(client))
    response = client.get("/api/v1/insights/anomalies", headers=headers)
    assert response.status_code == 200, response.text
    assert [item["kind"] for item in response.json()["anomalies"]] == ["VOIDS", "CASH_SHORT"]
    feed = client.get("/api/v1/insights/feed", headers=headers).json()["items"]
    assert any(item["kind"] == "anomaly" and "Eve" in item["body"] for item in feed)

    answer = client.post("/api/v1/assistant/ask", headers=headers, json={"question": "Any unusual voids this month?"})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["results"][0]["tool"] == "anomalies"
    assert "Eve" in body["answer"]


def test_anomalies_need_audit_access(client) -> None:
    assert client.get("/api/v1/insights/anomalies", headers={"X-Api-Key": "test-api-key-value"}).status_code == 403


def test_price_suggestions_mark_down_expiring_stock_and_lift_prices_under_the_floor(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    cable_batch(client, token, 12, "14.00")
    session.expire_all()
    item = session.scalar(select(BatchItem).where(BatchItem.product_id == uuid.UUID(CABLE_ID)))
    assert item is not None
    item.expiry_date = datetime.now(UTC).date() + timedelta(days=2)
    session.commit()
    record_sale(client, product_id=CABLE_ID, price=1500)
    policy = client.put(
        "/api/v1/margin/policies", headers=bearer(token), json={"scope": "GLOBAL", "min_margin_bps": 2000}
    )
    assert policy.status_code == 200, policy.text

    response = client.get("/api/v1/insights/pricing", headers=bearer(token))
    assert response.status_code == 200, response.text
    by_action = {row["action"]: row for row in response.json()["suggestions"] if row["product_id"] == CABLE_ID}
    floor = by_action["RAISE_TO_FLOOR"]
    assert floor["price_cents"] == 1500 and floor["suggested_price_cents"] >= 1700
    assert floor["suggested_price_cents"] % 50 == 0 and "margin floor" in floor["reason"]
    markdown = by_action["EXPIRY_MARKDOWN"]
    assert markdown["suggested_price_cents"] == 1050 and markdown["change_pct"] == -30
    assert markdown["on_hand"] == 11 and "write off" in markdown["reason"]
    assert insights_service.expiry_markdown_bps(1) == 5000 and insights_service.expiry_markdown_bps(6) == 2000


def test_shrink_is_valued_at_cost_by_reason_and_flags_hotspots(client) -> None:
    seed_catalog(client)
    token = admin_token(client)
    cable_batch(client, token, 10, "4.00")
    for quantity, reason in ((3, "STOLEN_SHRINKAGE"), (1, "DAMAGED_OR_EXPIRED")):
        adjusted = client.post(
            "/api/v1/inventory/adjust",
            headers=bearer(token),
            json={
                "adjustment_id": str(uuid.uuid4()),
                "product_id": CABLE_ID,
                "store_id": STORE_ID,
                "mode": "remove",
                "quantity": quantity,
                "reason_code": reason,
                "note": "Found missing on the shelf check",
            },
        )
        assert adjusted.status_code == 201, adjusted.text
    response = client.get("/api/v1/insights/shrink", headers=bearer(token), params={"days": 30})
    assert response.status_code == 200, response.text
    report = response.json()
    assert report["lost_cents"] == 1600 and report["net_cents"] == 1600
    assert [(row["label"], row["lost_cents"]) for row in report["by_reason"]] == [
        ("Theft", 1200),
        ("Damaged or expired", 400),
    ]
    product = report["top_products"][0]
    assert product["lost_units"] == 4 and product["events"] == 2 and product["shrink_rate_bps"] == 10_000
    assert report["hotspots"] and "no sales" in report["hotspots"][0]["summary"]


def test_weighed_shrink_counts_grams_against_per_kilo_cost(client, session: Session, monkeypatch) -> None:
    seed_catalog(client)
    product = Product(
        sku="FRU-BAN",
        barcode="2000000000017",
        name="Bananas",
        category="Fruit",
        price_cents=900,
        currency="USD",
        sold_by_weight=True,
    )
    session.add(product)
    session.flush()
    session.add(
        StockMovement(
            product_id=product.id,
            store_id=uuid.UUID(STORE_ID),
            movement_type="DAMAGE_SHRINKAGE",
            quantity=-750,
            quantity_after=0,
            reference_type="manual_adjustment",
            reason_code="DAMAGED_OR_EXPIRED",
        )
    )
    session.commit()
    monkeypatch.setattr(costing, "fallback_unit_cost", lambda db, product_id: 400)
    now = datetime.now(UTC)
    rows = management_reports.shrinkage(session, now - timedelta(days=1), now + timedelta(days=1), None)
    assert [value for _, _, value in rows] == [300]
