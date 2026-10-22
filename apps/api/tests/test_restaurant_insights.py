import random
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_returns import STORE_ID, admin_token, bearer

from app.core.deps import Principal
from app.models.kitchen import KitchenStation, KitchenTicket, KitchenTicketItem
from app.models.product import Product
from app.models.restaurant import DiningArea, DiningTable, OpenOrder
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.models.user import User
from app.services import restaurant_insights_service as insights

OWNER = Principal(kind="device", scope="device")
STORE = uuid.UUID(STORE_ID)


def store(session: Session) -> None:
    session.add(Store(id=STORE, code="DT-01", name="Downtown", currency="USD"))
    session.flush()


def product(session: Session, name: str, price: int = 1500) -> Product:
    row = Product(
        sku=name.upper().replace(" ", "-"),
        barcode=str(uuid.uuid4().int)[:13],
        name=name,
        category="Menu",
        price_cents=price,
        currency="USD",
    )
    session.add(row)
    session.flush()
    return row


def test_prep_model_recovers_how_items_and_the_queue_slow_the_kitchen() -> None:
    rng = random.Random(7)
    samples = []
    for _ in range(200):
        items, queued = rng.randint(1, 6), rng.randint(0, 8)
        samples.append((items, queued, 4 + 1.5 * items + 0.8 * queued + rng.uniform(-0.5, 0.5)))
    model = insights.fit_prep_model(samples)
    assert model is not None
    assert abs(model.base_minutes - 4) < 0.5
    assert abs(model.per_item_minutes - 1.5) < 0.1 and abs(model.per_queued_minutes - 0.8) < 0.1
    assert model.mae_minutes < model.baseline_mae_minutes / 4
    assert insights.fit_prep_model(samples[:5]) is None


def test_kitchen_report_flags_tickets_running_late(session: Session) -> None:
    store(session)
    station = KitchenStation(store_id=STORE, name="Grill", category_ids=[], is_default=True)
    session.add(station)
    session.flush()
    now = datetime.now(UTC)
    rng = random.Random(3)
    for index in range(60):
        fired = now - timedelta(days=1 + index % 20, minutes=index * 7)
        items = rng.randint(1, 4)
        ticket = KitchenTicket(
            store_id=STORE,
            station_id=station.id,
            number=index,
            label=f"T{index % 6}",
            service_type="DINE_IN",
            status="BUMPED",
            fired_at=fired,
            ready_at=fired + timedelta(minutes=5 + 2 * items),
            bumped_at=fired + timedelta(minutes=6 + 2 * items),
        )
        ticket.items = [KitchenTicketItem(product_name="Burger", quantity=items)]
        session.add(ticket)
    late = KitchenTicket(
        store_id=STORE,
        station_id=station.id,
        number=99,
        label="T9",
        service_type="DINE_IN",
        status="PREPARING",
        fired_at=now - timedelta(minutes=40),
    )
    late.items = [KitchenTicketItem(product_name="Burger", quantity=2)]
    session.add(late)
    session.commit()

    report = insights.kitchen(session, OWNER)
    grill = report.stations[0]
    assert grill.station_name == "Grill" and grill.tickets_28d == 61 and grill.open_tickets == 1
    assert grill.model is not None and abs(grill.model.per_item_minutes - 2) < 0.2
    assert grill.median_minutes is not None and 6 <= grill.median_minutes <= 14
    assert grill.live[0].number == 99 and grill.live[0].at_risk
    assert grill.wait_now_minutes is not None and grill.wait_now_minutes > 0


def test_tables_predict_when_open_tables_free_up(session: Session) -> None:
    store(session)
    owner = session.scalar(select(User).where(User.username == "admin"))
    assert owner is not None
    area = DiningArea(store_id=STORE, name="Main")
    session.add(area)
    session.flush()
    table = DiningTable(area_id=area.id, label="T1", seats=4)
    session.add(table)
    session.flush()
    now = datetime.now(UTC)
    for index in range(10):
        opened = now - timedelta(days=index + 1, hours=1)
        order = OpenOrder(
            store_id=STORE,
            number=index + 1,
            service_type="DINE_IN",
            status="SETTLED",
            table_id=table.id,
            covers=2,
            opened_by_id=owner.id,
            opened_at=opened,
            closed_at=opened + timedelta(minutes=45 + index),
        )
        session.add(order)
        session.flush()
        session.add(
            Sale(
                store_id=STORE,
                cashier_id=owner.id,
                status="completed",
                currency="USD",
                payment_method="cash",
                subtotal_cents=6000,
                tax_cents=0,
                total_cents=6000,
                amount_paid_cents=6000,
                due_balance_cents=0,
                client_sale_id=str(uuid.uuid4()),
                order_id=order.id,
            )
        )
    lingering = OpenOrder(
        store_id=STORE,
        number=50,
        service_type="DINE_IN",
        status="OPEN",
        table_id=table.id,
        covers=2,
        opened_by_id=owner.id,
        opened_at=now - timedelta(minutes=120),
    )
    session.add(lingering)
    session.commit()

    report = insights.tables(session, OWNER)
    assert report.dine_in_orders == 10 and report.median_minutes is not None and 45 <= report.median_minutes <= 55
    assert report.by_party[0].label == "1-2 guests" and report.by_party[0].orders == 10
    turn = report.tables[0]
    assert turn.label == "T1" and turn.turns == 10 and turn.turns_per_day == 1.0 and turn.revenue_cents == 60_000
    open_table = report.open_tables[0]
    assert open_table.lingering and open_table.elapsed_minutes >= 119
    assert open_table.predicted_free_at > now


def test_upsell_pairs_prompt_the_usual_add_on(client, session: Session) -> None:
    store(session)
    owner = session.scalar(select(User).where(User.username == "admin"))
    assert owner is not None
    burger, fries, cola, salad = (product(session, name) for name in ("Burger", "Fries", "Cola", "Salad"))
    baskets = [[burger, fries]] * 12 + [[burger, cola]] * 3 + [[salad, cola]] * 10 + [[salad]] * 5 + [[burger]] * 5
    for basket in baskets:
        sale = Sale(
            store_id=STORE,
            cashier_id=owner.id,
            status="completed",
            currency="USD",
            payment_method="cash",
            subtotal_cents=3000,
            tax_cents=0,
            total_cents=3000,
            amount_paid_cents=3000,
            due_balance_cents=0,
            client_sale_id=str(uuid.uuid4()),
        )
        session.add(sale)
        session.flush()
        for item in basket:
            session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=item.id,
                    quantity=1,
                    unit_price_cents=1500,
                    tax_cents=0,
                    line_total_cents=1500,
                )
            )
    session.commit()
    insights._upsell_cache.clear()

    prompt = insights.upsell(session, OWNER, product_ids=[burger.id])
    assert [pair.add_on_name for pair in prompt.pairs] == ["Fries"]
    assert prompt.pairs[0].confidence_bps == 6000
    assert "60% of guests who order Burger add Fries" in prompt.pairs[0].pitch
    already = insights.upsell(session, OWNER, product_ids=[burger.id, fries.id])
    assert all(pair.add_on_name != "Fries" for pair in already.pairs)

    response = client.get("/api/v1/insights/upsell", headers=bearer(admin_token(client)))
    assert response.status_code == 200, response.text
    names = {(row["product_name"], row["add_on_name"]) for row in response.json()["pairs"]}
    assert ("Burger", "Fries") in names and ("Salad", "Cola") in names

    answer = client.post(
        "/api/v1/assistant/ask",
        headers=bearer(admin_token(client)),
        json={"question": "What do guests usually order together?"},
    )
    assert answer.status_code == 200, answer.text
    assert answer.json()["results"][0]["tool"] == "upsell_pairs" and "Strongest" in answer.json()["answer"]
