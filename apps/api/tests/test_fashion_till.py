"""Fashion till essentials: gift cards, cashier discounts with limits and reasons, and the configurable returns
policy (fashion conditions, exchange-only window, final-sale items, refunds net of discounts)."""

import json
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuditLog
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.store_credit import StoreCredit
from app.models.user import User
from app.schemas.pos_policy import returns_preset
from app.seed_fashion import seed_fashion
from app.services import export_service
from wholesale_support import CABLE, CASHIER_ID, STORE, admin, device, event, line, push, sale, seed

GIFT = "GC-AAAA-BBBB-CCCC"


def fashion(client) -> dict[str, str]:
    headers, _ = admin(client)
    response = client.put(
        "/api/v1/settings/profile", headers=headers, json={"business_profile": "retail_fashion", "capabilities": None}
    )
    assert response.status_code == 200, response.text
    return headers


def push_sale(client, key: str, body: dict):
    return push(client, [event("fashion-" + key, "sale", body)])


def status(response) -> tuple[int, str]:
    result = response.json()["results"][0] if response.status_code == 200 else {}
    return response.status_code, result.get("status", response.text)


def sell_gift_card(client, code: str = GIFT, amount: int = 5000, key: str = "gift-1"):
    product = client.get("/api/v1/gift-cards/product", headers=device()).json()
    item = line(product["product_id"], 1, amount)
    item["gift_card_code"] = code
    return push_sale(client, key, sale([item])), product


def test_gift_cards_are_sold_spent_and_voided(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert client.get("/api/v1/gift-cards/product", headers=device()).status_code == 403
    fashion(client)

    sold, product = sell_gift_card(client)
    assert status(sold) == (200, "applied"), sold.text
    card = session.scalar(select(StoreCredit).where(StoreCredit.code == GIFT))
    assert (card.kind, card.balance_cents, card.expires_at is not None) == ("GIFT_CARD", 5000, True)
    assert product["sku"] == "SRV-GIFT-CARD"
    assert client.get(f"/api/v1/gift-cards/{GIFT}", headers=device()).json()["usable"] is True

    order = sale([line(CABLE, 2, 1500)], payment_method="gift_card")
    order["tenders"] = [{"method": "gift_card", "amount_cents": 3000, "gift_card_code": GIFT}]
    assert status(push_sale(client, "spend-1", order)) == (200, "applied")
    session.refresh(card)
    assert card.balance_cents == 2000

    too_much = sale([line(CABLE, 2, 1500)], payment_method="gift_card")
    too_much["tenders"] = [{"method": "gift_card", "amount_cents": 3000, "gift_card_code": GIFT}]
    rejected = push_sale(client, "spend-2", too_much)
    assert rejected.status_code == 422 and "only 20.00" in rejected.text

    item = line(product["product_id"], 1, 2000)
    item["gift_card_code"] = "GC-DDDD-EEEE-FFFF"
    card_for_card = sale([item], payment_method="gift_card")
    card_for_card["tenders"] = [{"method": "gift_card", "amount_cents": 2000, "gift_card_code": GIFT}]
    assert "another gift card" in push_sale(client, "card-for-card", card_for_card).text

    voided = client.post(f"/api/v1/gift-cards/{GIFT}/void", headers=headers, json={"note": "Reported stolen"})
    assert voided.status_code == 200 and voided.json()["usable"] is False
    after_void = sale([line(CABLE, 1, 1500)], payment_method="gift_card")
    after_void["tenders"] = [{"method": "gift_card", "amount_cents": 1500, "gift_card_code": GIFT}]
    assert "voided" in push_sale(client, "spend-3", after_void).text

    issued = client.post(
        "/api/v1/gift-cards/issue",
        headers=headers,
        json={"store_id": STORE, "amount_cents": 10000, "count": 3, "customer_id": None, "note": "Mall promotion"},
    )
    assert issued.status_code == 201 and len(issued.json()) == 3
    listing = client.get("/api/v1/gift-cards", headers=headers).json()
    assert listing["open_count"] == 3 and listing["outstanding_cents"] == 30000

    # wholesale_support stamps every sync event 2026-10-19, which becomes the sale date.
    today = date.today()
    lines = export_service.journal(session, date(2026, 10, 18), today + timedelta(days=1), None)
    liability = [row for row in lines if row.account == "2410"]
    assert sum(row.credit for row in liability) == 5000 and sum(row.debit for row in liability) == 3000
    revenue = sum(row.credit for row in lines if row.account == "4000")
    assert revenue == 3000


def test_gift_card_amount_must_fit_the_rules(client) -> None:
    seed(client)
    fashion(client)
    small, _ = sell_gift_card(client, amount=500, key="gift-small")
    assert small.status_code == 422 and "loaded with" in small.text
    bad = sale([line(CABLE, 1, 1500)])
    bad["items"][0]["gift_card_code"] = "GC-ZZZZ-ZZZZ-ZZZZ"
    assert "gift card product" in push_sale(client, "gift-wrong-product", bad).text


def discounted(product: str, quantity: int, unit: int, discount: int, reason: str = "staff", **extra) -> dict:
    item = line(product, quantity, unit)
    item.update(manual_discount_cents=discount, discount_reason=reason, line_total_cents=unit * quantity - discount)
    item.update(extra)
    return item


def test_cashier_discounts_follow_role_limits_and_reasons(client, session) -> None:
    seed(client)
    _, admin_id = admin(client)
    no_permission = sale([discounted(CABLE, 2, 1500, 300)])
    assert "needs a manager" in push_sale(client, "disc-1", no_permission).text

    approved = sale([discounted(CABLE, 2, 1500, 300, discount_override={"approved_by_id": admin_id, "note": "VIP"})])
    assert status(push_sale(client, "disc-2", approved)) == (200, "applied")
    entry = session.scalar(select(AuditLog).where(AuditLog.action == "sale.discount"))
    assert entry is not None and entry.approver_id == uuid.UUID(admin_id) and entry.details["reason"] == "staff"

    unknown = sale([discounted(CABLE, 1, 1500, 100, reason="birthday")])
    assert "not one of the business's reasons" in push_sale(client, "disc-3", unknown).text

    by_admin = sale([discounted(CABLE, 2, 1500, 1500, reason="damaged")], cashier_id=admin_id)
    assert status(push_sale(client, "disc-4", by_admin)) == (200, "applied")

    headers, _ = admin(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["role"]["max_discount_bps"] == 10_000
    report = client.get("/api/v1/reports/management/discounts?from=2026-10-01&to=2026-10-31", headers=headers).json()
    assert report["total_cents"] == 1800
    staff = next(row for row in report["rows"] if row["reason"] == "staff")
    assert (staff["lines"], staff["discount_cents"], staff["approved_lines"], staff["share_bps"]) == (1, 300, 1, 1000)
    assert [group["reason_label"] for group in report["by_reason"]] == ["Damaged or soiled item", "Staff discount"]
    csv = client.get("/api/v1/reports/management/discounts.csv?from=2026-10-01&to=2026-10-31", headers=headers)
    assert csv.status_code == 200 and "Staff discount" in csv.text


def test_gift_receipt_pdf_hides_prices(client) -> None:
    seed(client)
    headers, _ = admin(client)
    body = sale([line(CABLE, 1, 1500)])
    assert status(push_sale(client, "gift-receipt", body)) == (200, "applied")
    receipt = receipt_for(client, body["client_sale_id"])
    pdf = client.get(f"/api/v1/sales/{receipt['sale_id']}/gift-receipt.pdf", headers=headers)
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF") and b"15.00" not in pdf.content
    assert client.get(f"/api/v1/sales/{uuid.uuid4()}/gift-receipt.pdf", headers=headers).status_code == 404


def return_body(receipt_body: dict, *, condition: str, reason: str, tender: str = "cash", **extra) -> dict:
    item = receipt_body["items"][0]
    subtotal = item["unit_price_cents"] - item.get("discount_cents", 0) // item["quantity"]
    if item["quantity"] == 1:
        subtotal = item["unit_price_cents"] - item.get("discount_cents", 0)
    body = {
        "id": str(uuid.uuid4()),
        "original_sale_id": receipt_body["sale_id"],
        "store_id": STORE,
        "cashier_id": CASHIER_ID,
        "currency": "USD",
        "processed_at": datetime.now(UTC).isoformat(),
        "subtotal_cents": subtotal,
        "tax_refund_cents": 0,
        "restocking_fee_cents": 0,
        "total_refund_cents": subtotal,
        "reason_notes": "Customer return.",
        "items": [
            {
                "id": str(uuid.uuid4()),
                "sale_item_id": item["sale_item_id"],
                "product_id": item["product_id"],
                "quantity": 1,
                "unit_price_cents": item["unit_price_cents"],
                "tax_refund_cents": 0,
                "restocking_fee_cents": 0,
                "refund_cents": subtotal,
                "condition_status": condition,
                "reason_code": reason,
                "serial_value": None,
                "serial_kind": None,
            }
        ],
        "tenders": [{"method": tender, "amount_cents": subtotal, "store_credit_code": None}],
        "override": None,
    }
    body.update(extra)
    return body


def receipt_for(client, sale_id: str) -> dict:
    response = client.get(f"/api/v1/returns/receipts/{sale_id}", headers=device())
    assert response.status_code == 200, response.text
    return response.json()


def cable_on_hand(session) -> int:
    level = session.scalar(
        select(InventoryLevel).where(
            InventoryLevel.product_id == uuid.UUID(CABLE), InventoryLevel.store_id == uuid.UUID(STORE)
        )
    )
    session.refresh(level)
    return level.quantity_on_hand


def test_fashion_returns_policy(client, session) -> None:
    seed(client)
    headers = fashion(client)
    _, admin_id = admin(client)
    sold = sale([line(CABLE, 1, 1500)])
    assert status(push_sale(client, "ret-sale-1", sold)) == (200, "applied")
    body = receipt_for(client, sold["id"])
    assert body["policy"]["preset"] == "fashion"
    assert [row["key"] for row in body["policy"]["conditions"]] == ["tags_attached", "worn", "damaged"]
    assert body["policy"]["window_days"] == 14

    wrong = return_body(body, condition="open_box", reason="size_fit")
    assert "not in the returns policy" in push(client, [event("fashion-" + "ret-1", "sale_return", wrong)]).text

    before = cable_on_hand(session)
    good = return_body(
        body,
        condition="tags_attached",
        reason="size_fit",
        override={"approved_by_id": admin_id, "reasons": ["no_refund_permission"], "note": "Checked."},
    )
    response = push(client, [event("fashion-" + "ret-2", "sale_return", good)])
    assert status(response) == (200, "applied"), response.text
    assert cable_on_hand(session) == before + 1

    # 20 days old: outside the 14-day refund window, inside the 16-day exchange window -> voucher only.
    old = sale([line(CABLE, 1, 1500)], sold_at=(datetime.now(UTC) - timedelta(days=20)).isoformat())
    assert status(push_sale(client, "ret-sale-2", old)) == (200, "applied")
    old_receipt = receipt_for(client, old["id"])
    override = {"approved_by_id": admin_id, "reasons": ["no_refund_permission"], "note": "Checked."}
    cash = return_body(old_receipt, condition="worn", reason="style", override=override)
    assert "refund to Store credit" in push(client, [event("fashion-" + "ret-3", "sale_return", cash)]).text
    voucher = return_body(old_receipt, condition="worn", reason="style", tender="store_credit", override=override)
    voucher["tenders"][0]["store_credit_code"] = "SC-AAAA-BBBB-CCCC"
    assert status(push(client, [event("fashion-" + "ret-4", "sale_return", voucher)])) == (200, "applied")

    product = session.get(Product, uuid.UUID(CABLE))
    product.is_final_sale = True
    session.commit()
    final = sale([line(CABLE, 1, 1500)])
    assert status(push_sale(client, "ret-sale-3", final)) == (200, "applied")
    final_receipt = receipt_for(client, final["id"])
    assert final_receipt["items"][0]["final_sale"] is True
    blocked = return_body(final_receipt, condition="tags_attached", reason="size_fit", override=override)
    assert "final-sale" in push(client, [event("fashion-" + "ret-5", "sale_return", blocked)]).text
    allowed = return_body(
        final_receipt,
        condition="tags_attached",
        reason="size_fit",
        override={**override, "reasons": ["no_refund_permission", "final_sale"]},
    )
    assert status(push(client, [event("fashion-" + "ret-6", "sale_return", allowed)])) == (200, "applied")
    assert headers


def test_refunds_carry_their_share_of_the_discount(client) -> None:
    seed(client)
    _, admin_id = admin(client)
    sold = sale([discounted(CABLE, 1, 1500, 300, discount_override={"approved_by_id": admin_id, "note": "VIP"})])
    assert status(push_sale(client, "disc-ret-sale", sold)) == (200, "applied")
    body = receipt_for(client, sold["id"])
    assert body["items"][0]["discount_cents"] == 300
    override = {"approved_by_id": admin_id, "reasons": ["no_refund_permission"], "note": "Checked."}
    full_price = return_body(body, condition="unopened_resealable", reason="changed_mind", override=override)
    full_price["items"][0]["refund_cents"] = 1500
    full_price.update(subtotal_cents=1500, total_refund_cents=1500)
    full_price["tenders"][0]["amount_cents"] = 1500
    assert "discount" in push(client, [event("fashion-" + "disc-ret-1", "sale_return", full_price)]).text
    net = return_body(body, condition="unopened_resealable", reason="changed_mind", override=override)
    assert net["total_refund_cents"] == 1200
    assert status(push(client, [event("fashion-" + "disc-ret-2", "sale_return", net)])) == (200, "applied")


def test_till_rules_are_edited_by_business_admins(client) -> None:
    headers, _ = admin(client)
    current = client.get("/api/v1/settings", headers=headers).json()["pos_policy"]
    current["discounts"]["default_limit_bps"] = 1500
    current["returns"] = {**current["returns"], "window_days": 7}
    saved = client.put("/api/v1/settings/pos-policy", headers=headers, json=current)
    assert saved.status_code == 200, saved.text
    assert saved.json()["pos_policy"]["discounts"]["default_limit_bps"] == 1500
    assert saved.json()["pos_policy"]["returns"]["window_days"] == 7
    duplicate = {**current, "discounts": {**current["discounts"], "reasons": [{"key": "a1", "label": "A"}] * 2}}
    assert client.put("/api/v1/settings/pos-policy", headers=headers, json=duplicate).status_code == 422


def test_fashion_seed_has_till_demo_data(client, session) -> None:
    seed(client)
    fashion(client)
    user = session.scalar(select(User).where(User.username == "admin"))
    report = seed_fashion(session, get_settings(), user=user)
    assert any("gift cards sold" in line for line in report), report
    assert any("cashier discounts" in line and line.startswith("4 ") for line in report), report[-6:]
    cards = session.scalars(select(StoreCredit).where(StoreCredit.kind == "GIFT_CARD")).all()
    assert len(cards) == 5
    assert session.scalar(select(Product).where(Product.is_final_sale.is_(True))) is not None
    again = seed_fashion(session, get_settings(), user=user)
    assert again == ["catalogue already complete", "till demo already seeded (unchanged)"]


def test_bundled_seed_policy_matches_the_server_default() -> None:
    """A register that has never synced uses packages/catalog/seed.json; it must agree with the API's defaults."""
    seed_file = Path(__file__).resolve().parents[3] / "packages" / "catalog" / "seed.json"
    bundled = json.loads(seed_file.read_text(encoding="utf-8"))["return_policy"]
    default = returns_preset("electronics")
    assert bundled["window_days"] == default.window_days
    assert bundled["exchange_window_days"] == default.exchange_window_days
    assert bundled["conditions"] == [condition.model_dump() for condition in default.conditions]
    assert bundled["reasons"] == [reason.model_dump() for reason in default.reasons]
    assert bundled["serial_status_by_condition"] == {c.key: c.serial_status for c in default.conditions}
