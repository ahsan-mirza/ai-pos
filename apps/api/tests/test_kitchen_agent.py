import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session
from tests.test_menu import enable
from tests.test_recipes import ingredient
from tests.test_returns import CABLE_ID, STORE_ID, admin_id, admin_token, bearer, seed_catalog
from tests.test_weighed import category

from app.models import BatchItem, InventoryLevel, PurchaseBatch
from app.services.batch_ledger import today


def test_kitchen_brief_orders_a_low_ingredient_and_flags_an_expiring_batch(client, session: Session) -> None:
    seed_catalog(client)
    token = admin_token(client)
    enable(client, token, "menu_modifiers", "recipes")
    pantry = category(client, token)
    beans = ingredient(client, token, "Kitchen beans", quantity=5, by_weight=False, category_id=pantry)
    saved = client.put(
        f"/api/v1/recipes/{CABLE_ID}",
        headers=bearer(token),
        json={"yield_quantity": 1, "lines": [{"ingredient_id": beans["id"], "quantity": 18}]},
    )
    assert saved.status_code == 200, saved.text

    level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(beans["id"]),
            InventoryLevel.store_id == uuid.UUID(STORE_ID),
        )
    )
    assert level is not None
    level.min_reorder_level = 20
    batch = PurchaseBatch(
        batch_number=f"KIT-{uuid.uuid4().hex[:8]}",
        store_id=uuid.UUID(STORE_ID),
        import_source="MANUAL",
        total_cost_amount=500,
        total_items_count=5,
        currency="AED",
        status="ACTIVE",
        created_by_id=uuid.UUID(admin_id(client)),
    )
    session.add(batch)
    session.flush()
    session.add(
        BatchItem(
            batch_id=batch.id,
            product_id=uuid.UUID(beans["id"]),
            store_id=uuid.UUID(STORE_ID),
            quantity_imported=5,
            quantity_remaining=5,
            purchase_cost_per_unit=100,
            selling_price_per_unit=0,
            expiry_date=today() + timedelta(days=1),
        )
    )
    session.commit()

    response = client.get("/api/v1/kitchen-agent", headers=bearer(token))
    assert response.status_code == 200, response.text
    kinds = {card["kind"] for card in response.json()["cards"]}
    assert "order" in kinds
    assert kinds & {"use_first", "push_today", "write_off"}
