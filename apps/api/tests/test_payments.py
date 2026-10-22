import hashlib
import hmac
import json

from app.core.config import get_settings
from app.services.payment_service import crc16_ccitt, emvco_payload
from wholesale_support import CABLE, STORE, device, event, line, push, sale, seed


def test_emvco_payload_is_tlv_with_valid_crc() -> None:
    settings = get_settings().model_copy(update={"emvco_merchant_account": "MID123"})
    payload = emvco_payload(settings, amount_cents=12_345, currency="AED", reference="AIPTEST1")
    assert payload.startswith("000201010212")
    assert "5303784" in payload and "5406123.45" in payload and "5802AE" in payload
    assert crc16_ccitt(payload[:-4]) == payload[-4:]
    assert crc16_ccitt("123456789") == "29B1"


def test_dev_qr_payment_pays_one_sale_only(client) -> None:
    seed(client)
    intent = client.post("/api/v1/payments/intents", headers=device(), json={"amount_cents": 3000, "store_id": STORE})
    assert intent.status_code == 201, intent.text
    data = intent.json()
    assert data["qr_payload"].endswith(f"/payments/dev/{data['id']}/pay")

    unpaid = sale(
        [line(CABLE, 2, 1500)],
        payment_method="qr",
        tenders=[{"method": "qr", "amount_cents": 3000, "payment_intent_id": data["id"]}],
    )
    assert push(client, [event("qr-unpaid-sale", "sale", unpaid)]).status_code == 422

    assert client.get(f"/api/v1/payments/dev/{data['id']}/pay").json()["status"] == "PAID"
    assert client.get(f"/api/v1/payments/intents/{data['id']}", headers=device()).json()["status"] == "PAID"
    paid = {**unpaid, "id": unpaid["id"]}
    response = push(client, [event("qr-paid-sale", "sale", paid)])
    assert response.status_code == 200, response.text

    again = sale(
        [line(CABLE, 2, 1500)],
        payment_method="qr",
        tenders=[{"method": "qr", "amount_cents": 3000, "payment_intent_id": data["id"]}],
    )
    reused = push(client, [event("qr-reused-sale", "sale", again)])
    assert reused.status_code == 422 and "another sale" in reused.json()["error"]["message"]


def test_webhook_requires_signature(client) -> None:
    seed(client)
    settings = get_settings()
    settings.payment_webhook_secret = "whsec-test-value"
    try:
        intent = client.post(
            "/api/v1/payments/intents", headers=device(), json={"amount_cents": 500, "store_id": STORE}
        ).json()
        body = json.dumps({"reference": intent["reference"], "status": "paid", "amount_cents": 500}).encode()
        bad = client.post("/api/v1/payments/webhooks/dev", content=body, headers={"X-Signature": "nope"})
        assert bad.status_code == 401
        signature = hmac.new(b"whsec-test-value", body, hashlib.sha256).hexdigest()
        good = client.post("/api/v1/payments/webhooks/dev", content=body, headers={"X-Signature": signature})
        assert good.status_code == 200 and good.json()["status"] == "PAID"
    finally:
        settings.payment_webhook_secret = None
