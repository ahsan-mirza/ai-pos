import json
import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import Principal
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.user import User
from app.schemas.assistant import AssistantAsk
from app.services import assistant_service, sales_velocity
from app.services.assistant_service import detect_language, plan
from app.services.assistant_tools import resolve_period
from wholesale_support import CABLE, admin, device, event, line, push, sale, seed


def test_plans_questions_in_english_and_arabic() -> None:
    assert detect_language("كم بعنا اليوم؟") == "ar"
    assert detect_language("How much did DT-01 sell?") == "en"
    assert plan("How much did we sell yesterday at dt-01?", ["DT-01"]).__dict__ == {
        "tool": "sales_summary",
        "args": {"period": "yesterday", "store_code": "DT-01"},
    }
    assert plan("Top 5 products by units last month", []).__dict__ == {
        "tool": "top_products",
        "args": {"period": "last_month", "limit": 5, "by": "quantity"},
    }
    assert plan("Which products have not sold in 180 days?", []).__dict__ == {
        "tool": "slow_stock",
        "args": {"dead_days": 180},
    }
    assert plan("Show slow stock for 90 days", []).__dict__ == {
        "tool": "slow_stock",
        "args": {"slow_days": 90},
    }
    assert plan("Which fast movers should we reprice?", []).__dict__ == {
        "tool": "price_suggestions",
        "args": {"action": "RAISE_ON_DEMAND"},
    }
    assert plan("Which cashier sold the most this week?", []).tool == "staff_performance"
    assert plan("كم الربح هذا الشهر؟", []).__dict__ == {
        "tool": "profit_and_loss",
        "args": {"period": "this_month"},
    }
    assert plan("ما هي المنتجات الأكثر مبيعًا الشهر الماضي؟", []).__dict__ == {
        "tool": "top_products",
        "args": {"period": "last_month"},
    }
    assert plan("profit in September", []).args == {"month": 9}
    assert plan("What's the weather?", []) is None
    assert plan("hello", []) is None
    assert plan("what is my net slae", []).__dict__ == {"tool": "sales_summary", "args": {}}
    assert plan("what is my net sales", []).__dict__ == {"tool": "sales_summary", "args": {}}
    assert plan("How much do we owe suppliers?", []).tool == "payables_due"


def test_periods_resolve_to_calendar_ranges() -> None:
    today = date(2026, 10, 21)
    assert resolve_period({"period": "this_week"}, "today", today).start == date(2026, 10, 19)
    last_month = resolve_period({"period": "last_month"}, "today", today)
    assert (last_month.start, last_month.end) == (date(2026, 9, 1), date(2026, 9, 30))
    assert resolve_period({"month": 12}, "today", today).start == date(2025, 12, 1)
    custom = resolve_period({"from": "2026-10-01", "to": "2026-10-10"}, "today", today)
    assert (custom.start, custom.end) == (date(2026, 10, 1), date(2026, 10, 10))
    assert resolve_period({"period": "nonsense"}, "this_month", today).start == date(2026, 10, 1)


@pytest.fixture
def sold(client):
    seed(client)
    body = sale([line(CABLE, 4, 1500)], payment_method="card", tenders=[{"method": "card", "amount_cents": 6_000}])
    assert push(client, [event("assistant-sale", "sale", body)]).status_code == 200
    return admin(client)[0]


def test_builtin_answers_from_the_reports(client, sold) -> None:
    question = {"question": "How much did we sell between 2026-10-19 and today?", "history": []}
    reply = client.post("/api/v1/assistant/ask", headers=sold, json={"question": "Sales in the last 400 days"})
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["provider"] == "builtin" and body["language"] == "en"
    assert "USD 60.00" in body["answer"] and "1 sales" in body["answer"]
    assert body["results"][0]["rows"][0][0] == "DT-01"
    assert client.post("/api/v1/assistant/ask", headers=sold, json=question).status_code == 200

    arabic = client.post(
        "/api/v1/assistant/ask", headers=sold, json={"question": "ما هي طرق الدفع آخر 400 يوم؟"}
    ).json()
    assert arabic["language"] == "ar"
    assert "بطاقة" in arabic["answer"]

    unknown = client.post("/api/v1/assistant/ask", headers=sold, json={"question": "Tell me a joke"}).json()
    assert unknown["results"] == [] and "only answer from your reports" in unknown["answer"]

    info = client.get("/api/v1/assistant", headers=sold).json()
    assert info["provider"] == "builtin" and "payables_due" in info["tools"]


def test_openai_provider_calls_tools_and_falls_back(client, sold, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "assistant_provider", "openai")
    monkeypatch.setattr(settings, "assistant_api_key", "sk-test")
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if len(seen) == 1:
            assert {tool["function"]["name"] for tool in body["tools"]} >= {"sales_summary", "payables_due"}
            call = {
                "id": "c1",
                "type": "function",
                "function": {"name": "sales_summary", "arguments": '{"from": "2026-01-01", "to": "2026-12-31"}'},
            }
            return httpx.Response(
                200, json={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [call]}}]}
            )
        tool_message = body["messages"][-1]
        assert tool_message["role"] == "tool" and "USD 60.00" in tool_message["content"]
        return httpx.Response(
            200, json={"choices": [{"message": {"role": "assistant", "content": "You sold USD 60.00 this year."}}]}
        )

    real_client = httpx.Client
    monkeypatch.setattr(
        assistant_service.httpx, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handler))
    )
    reply = client.post(
        "/api/v1/assistant/ask", headers=sold, json={"question": "How much did we sell this year?"}
    ).json()
    assert reply["provider"] == "openai:gpt-4o-mini"
    assert reply["answer"] == "You sold USD 60.00 this year."
    assert reply["results"][0]["tool"] == "sales_summary"

    monkeypatch.setattr(
        assistant_service.httpx,
        "Client",
        lambda **kwargs: real_client(transport=httpx.MockTransport(lambda request: httpx.Response(500))),
    )
    fallback = client.post(
        "/api/v1/assistant/ask", headers=sold, json={"question": "Sales in the last 400 days"}
    ).json()
    assert fallback["provider"] == "builtin (fallback)"
    assert "USD 60.00" in fallback["answer"]


def test_assistant_respects_permissions(client, session) -> None:
    seed(client)
    user = session.query(User).filter(User.username == "admin").one()
    reports_only = Principal(kind="user", scope="portal", user=user, permissions=frozenset({"portal:reports_read"}))
    blocked = assistant_service.ask(
        session, reports_only, get_settings(), AssistantAsk(question="How much do we owe suppliers?")
    )
    assert blocked.results == [] and "does not include that report" in blocked.answer
    cashier = client.post(
        "/api/v1/auth/login-pin", json={"username": "cashier", "pin": "1357"}, headers=device()
    ).json()
    denied = client.post(
        "/api/v1/assistant/ask",
        headers={"Authorization": f"Bearer {cashier['access_token']}"},
        json={"question": "How much did we sell today?"},
    )
    assert denied.status_code == 403


def test_top_products_uses_base_units_and_nets_returns(client, session) -> None:
    seed(client)
    headers, _ = admin(client)
    assert push(client, [event("rank-sale", "sale", sale([line(CABLE, 4, 1500)]))]).status_code == 200
    sold = session.scalar(select(Sale))
    item = session.scalar(select(SaleItem).where(SaleItem.product_id == uuid.UUID(CABLE)))
    assert sold is not None and item is not None
    sold.created_at = datetime.now(UTC) - timedelta(days=1)
    item.unit_factor = 24
    session.commit()
    answer = client.post(
        "/api/v1/assistant/ask", headers=headers, json={"question": "Top products by units this month"}
    ).json()
    cable = next(row for row in answer["results"][0]["rows"] if row[1] == "ACC-CABLE-USBC")
    assert cable[2] == "4"
    assert answer["results"][0]["tool"] == "top_products"

    now = datetime.now(UTC)
    ranked = sales_velocity.rank_products(
        session,
        since=now - timedelta(days=30),
        until=now + timedelta(days=1),
        category="Accessories",
        by="quantity",
    )
    assert ranked[0].units == 4 and ranked[0].sku == "ACC-CABLE-USBC"
    assert (
        sales_velocity.rank_products(
            session, since=now - timedelta(days=30), until=now + timedelta(days=1), category="Phones", by="quantity"
        )
        == []
    )

    returned = SaleReturn(
        original_sale_id=sold.id,
        store_id=sold.store_id,
        cashier_id=sold.cashier_id,
        currency="USD",
        subtotal_cents=1500,
        tax_refund_cents=0,
        restocking_fee_cents=0,
        total_refund_cents=1500,
        refund_method="cash",
        reason_notes="",
    )
    session.add(returned)
    session.flush()
    session.add(
        ReturnItem(
            return_id=returned.id,
            sale_item_id=item.id,
            product_id=item.product_id,
            quantity=1,
            unit_price_cents=1500,
            tax_refund_cents=0,
            restocking_fee_cents=0,
            refund_cents=1500,
            condition_status="unopened_resealable",
            reason_code="changed_mind",
        )
    )
    session.commit()
    net = sales_velocity.rank_products(
        session, since=now - timedelta(days=30), until=now + timedelta(days=1), by="quantity"
    )
    cable_rank = next(row for row in net if row.sku == "ACC-CABLE-USBC")
    assert cable_rank.units == 3 and cable_rank.revenue_cents == item.line_total_cents - 1500
