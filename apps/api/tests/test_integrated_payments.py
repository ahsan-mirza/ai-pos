import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations import http as provider_http
from app.integrations.http import sign
from app.integrations.payments.base import PaymentRef, StartRequest
from app.integrations.payments.ngenius import NGeniusAdapter
from app.integrations.payments.simulator import FAILING_REFUND_CENTS
from app.integrations.payments.tamara import TamaraAdapter
from app.jobs.runner import run_job
from app.models import AuditLog, PaymentIntent, PaymentRefund
from test_returns import admin_id, approval, receipt, return_payload
from test_returns import push as push_one
from wholesale_support import CABLE, STORE, admin, device, event, line, push, sale, seed


@pytest.fixture(autouse=True)
def _no_network():
    yield
    provider_http.use_transport(None)


def _terminal(client, headers, **extra) -> dict:
    body = {"store_id": STORE, "provider": "simulator", "terminal_ref": "SIM-01", "label": "Counter 1", **extra}
    response = client.post("/api/v1/payments/terminals", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _card(client, amount: int) -> dict:
    response = client.post(
        "/api/v1/payments/card-intents", headers=device(), json={"amount_cents": amount, "store_id": STORE}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _simulate(client, intent_id: str, outcome: str = "approve") -> dict:
    response = client.post(
        f"/api/v1/payments/intents/{intent_id}/simulate", headers=device(), json={"outcome": outcome}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_card_terminal_payment_pays_one_sale_and_refunds_to_the_card(client, session: Session) -> None:
    seed(client)
    headers, _ = admin(client)
    terminal = _terminal(client, headers)
    config = client.get("/api/v1/payments/config", headers=device(), params={"store_id": STORE}).json()
    assert config["card_terminal_required"] is True and config["default_terminal_id"] == terminal["id"]
    assert config["simulator_controls"] is True

    intent = _card(client, 3000)
    assert intent["channel"] == "CARD" and intent["status"] == "PENDING" and intent["simulated"] is True
    unpaid = sale(
        [line(CABLE, 2, 1500)],
        payment_method="card",
        tenders=[{"method": "card", "amount_cents": 3000, "payment_intent_id": intent["id"]}],
    )
    assert push(client, [event("card-unpaid", "sale", unpaid)]).status_code == 422

    paid = _simulate(client, intent["id"])
    assert paid["status"] == "PAID" and paid["auth_code"] and paid["card_last4"]
    assert push(client, [event("card-paid", "sale", unpaid)]).status_code == 200

    again = sale(
        [line(CABLE, 2, 1500)],
        payment_method="card",
        tenders=[{"method": "card", "amount_cents": 3000, "payment_intent_id": intent["id"]}],
    )
    reused = push(client, [event("card-reused", "sale", again)])
    assert reused.status_code == 422 and "another sale" in reused.json()["error"]["message"]

    body = receipt(client, unpaid["id"])
    returned = push_one(
        client, "sale_return", return_payload(body, tender="original_card", override=approval(admin_id(client)))
    )
    assert returned.status_code == 200, returned.text
    refund = session.query(PaymentRefund).one()
    assert refund.status == "PENDING" and refund.amount_cents == 1500

    assert run_job(session, get_settings(), "payment_refunds") == "ok"
    session.expire_all()
    assert session.get(PaymentRefund, refund.id).status == "SUCCEEDED"
    assert session.get(PaymentIntent, refund.intent_id).refunded_cents == 1500

    shift_totals = client.get("/api/v1/payments/list", headers=headers, params={"channel": "CARD"}).json()
    assert shift_totals["total"] == 1 and shift_totals["refunded_cents"] == 1500
    assert shift_totals["items"][0]["sale_number"]


def test_declines_and_manual_card_entries_are_audited(client, session: Session) -> None:
    seed(client)
    headers, admin_user = admin(client)
    _terminal(client, headers)
    declined = _simulate(client, _card(client, 1500)["id"], "decline")
    assert declined["status"] == "DECLINED" and "simulated" in declined["failure_reason"]

    now = datetime.now(UTC).isoformat()
    manual = sale([line(CABLE, 1, 1500)], payment_method="card", sold_at=now)
    assert push(client, [event("manual-unapproved", "sale", manual)]).status_code == 200
    approved = sale(
        [line(CABLE, 1, 1500)],
        payment_method="card",
        sold_at=now,
        tenders=[
            {
                "method": "card",
                "amount_cents": 1500,
                "manual_override": {"approved_by_id": admin_user, "note": "Terminal offline"},
            }
        ],
    )
    assert push(client, [event("manual-approved", "sale", approved)]).status_code == 200
    actions = {row.action for row in session.query(AuditLog).filter(AuditLog.action.like("sale.manual_card%"))}
    assert actions == {"sale.manual_card_unapproved", "sale.manual_card_entry"}


def test_terminal_timeout_expires_the_payment(client, session: Session) -> None:
    seed(client)
    headers, _ = admin(client)
    _terminal(client, headers)
    intent = _card(client, 2000)
    row = session.get(PaymentIntent, uuid.UUID(intent["id"]))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    polled = client.get(f"/api/v1/payments/intents/{intent['id']}", headers=device()).json()
    assert polled["status"] == "EXPIRED"
    late = client.post(
        f"/api/v1/payments/intents/{intent['id']}/simulate", headers=device(), json={"outcome": "approve"}
    )
    assert late.json()["status"] == "EXPIRED"


def test_failed_refunds_are_kept_for_retry(client, session: Session) -> None:
    seed(client)
    headers, _ = admin(client)
    _terminal(client, headers)
    amount = FAILING_REFUND_CENTS
    intent = _card(client, amount)
    _simulate(client, intent["id"])
    sold = sale(
        [line(CABLE, 1, amount)],
        payment_method="card",
        tenders=[{"method": "card", "amount_cents": amount, "payment_intent_id": intent["id"]}],
    )
    assert push(client, [event("fail-sale", "sale", sold)]).status_code == 200
    body = receipt(client, sold["id"])
    payload = return_payload(body, tender="original_card", override=approval(admin_id(client)))
    assert push_one(client, "sale_return", payload).status_code == 200

    run_job(session, get_settings(), "payment_refunds")
    refunds = client.get("/api/v1/payments/refunds", headers=headers, params={"status": "FAILED"}).json()
    assert len(refunds) == 1 and refunds[0]["attempts"] == 1 and "Simulated refund failure" in refunds[0]["error"]
    retried = client.post(f"/api/v1/payments/refunds/{refunds[0]['id']}/retry", headers=headers)
    assert retried.status_code == 200 and retried.json()["attempts"] == 2


def test_simulated_bnpl_checkout_page_approves_and_refunds(client, session: Session) -> None:
    seed(client)
    created = client.post(
        "/api/v1/payments/bnpl-intents",
        headers=device(),
        json={"amount_cents": 3000, "store_id": STORE, "provider": "simulator", "customer_phone": "+971501234567"},
    )
    assert created.status_code == 201, created.text
    intent = created.json()
    assert intent["channel"] == "BNPL" and intent["customer_url"].endswith(f"/checkout/{intent['id']}")
    path = intent["customer_url"].split("/api/v1", 1)[1]
    page = client.get(f"/api/v1{path}")
    assert page.status_code == 200 and "Approve plan" in page.text
    decided = client.post(f"/api/v1{path}", data={"outcome": "approve"})
    assert decided.status_code == 200 and "Approved" in decided.text
    assert client.get(f"/api/v1/payments/intents/{intent['id']}", headers=device()).json()["status"] == "PAID"

    missing = sale([line(CABLE, 2, 1500)], payment_method="bnpl", tenders=[{"method": "bnpl", "amount_cents": 3000}])
    assert push(client, [event("bnpl-no-intent", "sale", missing)]).status_code == 422
    sold = sale(
        [line(CABLE, 2, 1500)],
        payment_method="bnpl",
        tenders=[{"method": "bnpl", "amount_cents": 3000, "payment_intent_id": intent["id"]}],
    )
    assert push(client, [event("bnpl-sale", "sale", sold)]).status_code == 200

    body = receipt(client, sold["id"])
    cash = push_one(client, "sale_return", return_payload(body, tender="cash", override=approval(admin_id(client))))
    assert cash.status_code == 422 and "pay-later provider" in cash.json()["error"]["message"]
    payload = return_payload(body, tender="original_bnpl", override=approval(admin_id(client)))
    assert push_one(client, "sale_return", payload).status_code == 200
    run_job(session, get_settings(), "payment_refunds")
    assert session.query(PaymentRefund).one().status == "SUCCEEDED"


def test_tabby_checkout_is_captured_when_authorized(client, session: Session) -> None:
    seed(client)
    settings = get_settings()
    saved = (settings.bnpl_providers, settings.tabby_secret_key, settings.tabby_merchant_code)
    settings.bnpl_providers, settings.tabby_secret_key, settings.tabby_merchant_code = "tabby", "sk_test", "AIPOS"
    settings.integration_webhook_secret = "whsec-integration"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        assert request.headers["authorization"] == "Bearer sk_test"
        if request.url.path == "/api/v2/checkout":
            sent = json.loads(request.content)
            assert sent["payment"]["amount"] == "30.00" and sent["merchant_code"] == "AIPOS"
            return httpx.Response(
                200,
                json={
                    "status": "created",
                    "payment": {"id": "pay_1", "status": "CREATED"},
                    "configuration": {
                        "available_products": {"installments": [{"web_url": "https://checkout.tabby.ai/x"}]}
                    },
                },
            )
        if request.url.path == "/api/v2/payments/pay_1" and request.method == "GET":
            return httpx.Response(200, json={"id": "pay_1", "status": "AUTHORIZED", "amount": "30.00"})
        if request.url.path == "/api/v2/payments/pay_1/captures":
            return httpx.Response(
                200, json={"id": "pay_1", "status": "CLOSED", "amount": "30.00", "captures": [{"amount": "30.00"}]}
            )
        return httpx.Response(404, json={"error": "unexpected"})

    provider_http.use_transport(httpx.MockTransport(handler))
    try:
        created = client.post(
            "/api/v1/payments/bnpl-intents",
            headers=device(),
            json={
                "amount_cents": 3000,
                "store_id": STORE,
                "provider": "tabby",
                "customer_phone": "+971500000001",
                "items": [{"name": "USB-C Cable", "quantity": 2, "unit_cents": 1500}],
            },
        ).json()
        assert created["status"] == "PENDING" and created["customer_url"] == "https://checkout.tabby.ai/x"
        assert created["simulated"] is False
        polled = client.get(f"/api/v1/payments/intents/{created['id']}", headers=device()).json()
        assert polled["status"] == "PAID"
        assert "POST /api/v2/payments/pay_1/captures" in calls

        body = json.dumps({"id": "pay_1", "status": "closed"}).encode()
        bad = client.post("/api/v1/integrations/payments/tabby/webhook", content=body, headers={"X-Signature": "x"})
        assert bad.status_code == 401
        good = client.post(
            "/api/v1/integrations/payments/tabby/webhook",
            content=body,
            headers={"X-Signature": sign("whsec-integration", body)},
        )
        assert good.status_code == 200 and good.json()["status"] == "PAID"
    finally:
        settings.bnpl_providers, settings.tabby_secret_key, settings.tabby_merchant_code = saved
        settings.integration_webhook_secret = None


def test_tamara_notifications_need_a_signed_token() -> None:
    secret, wrong = "notify-secret-for-tests-0123456789", "another-secret-for-tests-987654321"
    adapter = TamaraAdapter(api_token="t", notification_token=secret, base_url="https://x", timeout=5)
    token = jwt.encode({"iss": "Tamara"}, secret, algorithm="HS256")
    assert adapter.verify_webhook(b"{}", {}, {"tamaraToken": token})
    assert not adapter.verify_webhook(b"{}", {}, {"tamaraToken": jwt.encode({}, wrong, algorithm="HS256")})
    event = adapter.parse_webhook({"order_id": "o1", "order_reference_id": "AIP1", "order_status": "approved"})
    assert event.status.status == "AUTHORIZED" and event.reference == "AIP1"


def test_ngenius_pushes_the_sale_to_the_terminal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/identity/auth/access-token":
            assert request.headers["authorization"] == "Basic key"
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 300})
        assert request.headers["authorization"] == "Bearer tok"
        if request.url.path.endswith("/terminals/T1/sales"):
            assert json.loads(request.content)["amount"] == {"currencyCode": "AED", "value": 4500}
            return httpx.Response(201, json={"reference": "s1", "state": "AWAITING_CARD"})
        return httpx.Response(
            200,
            json={
                "reference": "s1",
                "state": "CAPTURED",
                "authCode": "A1",
                "paymentMethod": {"pan": "411111******1111"},
            },
        )

    provider_http.use_transport(httpx.MockTransport(handler))
    adapter = NGeniusAdapter(api_key="key", outlet_ref="OUT", base_url="https://ng", timeout=5, secret=None)
    started = adapter.start(
        StartRequest(intent_id="i", reference="AIP1", amount_cents=4500, currency="AED", terminal_ref="T1")
    )
    assert started.status == "PENDING" and started.provider_ref == "s1"
    fetched = adapter.fetch(
        PaymentRef(provider_ref="s1", reference="AIP1", amount_cents=4500, currency="AED", terminal_ref="T1")
    )
    assert fetched.status == "PAID" and fetched.auth_code == "A1" and fetched.card_last4 == "1111"
