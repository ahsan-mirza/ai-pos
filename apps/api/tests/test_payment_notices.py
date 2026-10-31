"""Console operators see a pending-payment count. A store session does not."""

import uuid

import pytest
from starlette.websockets import WebSocketDisconnect
from tests.governance_support import platform  # noqa: F401
from tests.test_bank_transfers import PNG, _pending_invoice, _submit

from app.tenancy.models import BillingTransfer, ConsolePaymentNotice


def _summary(host, headers) -> int:
    response = host.client.get("/api/v1/super-admin/billing/review-summary", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["pending"]


def _notices(host, headers) -> list[dict]:
    response = host.client.get("/api/v1/super-admin/billing/review-notices", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_pending_count_follows_review_and_ignores_a_repeated_submission(platform) -> None:  # noqa: F811
    admin = platform.operator(email="pay-admin@axizpos.com")
    support = platform.operator(email="pay-support@axizpos.com", role="SUPPORT")
    assert _summary(platform, admin) == 0
    assert _notices(platform, admin) == []
    invoice_id = _pending_invoice(platform)
    submitted = _submit(platform, invoice_id, "notice-transfer-1")
    assert _summary(platform, admin) == 1
    assert _summary(platform, support) == 1
    again = _submit(platform, invoice_id, "notice-transfer-1")
    assert again["id"] == submitted["id"]
    assert _summary(platform, admin) == 1
    notices = _notices(platform, admin)
    assert len(notices) == 1
    assert notices[0]["payment_submission_id"] == submitted["id"]
    assert notices[0]["status"] == "pending_review"
    assert notices[0]["read"] is False
    assert "bank" not in notices[0]
    second = _pending_invoice(platform, "bravo")
    _submit_for(platform, "bravo", second, "notice-transfer-2")
    assert _summary(platform, admin) == 2
    with platform.control() as db:
        assert db.query(ConsolePaymentNotice).count() == 2


def test_store_session_cannot_read_console_payment_notices(platform) -> None:  # noqa: F811
    denied = platform.client.get("/api/v1/super-admin/billing/review-summary", headers=platform.headers("alpha"))
    assert denied.status_code == 401
    missing = platform.client.get("/api/v1/super-admin/billing/review-summary")
    assert missing.status_code == 401


def test_verify_and_reject_decrease_the_count_and_reading_does_not(platform) -> None:  # noqa: F811
    admin = platform.operator(email="decide-admin@axizpos.com")
    invoice_id = _pending_invoice(platform)
    submitted = _submit(platform, invoice_id, "decide-transfer-1")
    notices = _notices(platform, admin)
    read = platform.client.post(
        f"/api/v1/super-admin/billing/review-notices/{notices[0]['id']}/read",
        headers=admin,
        json={},
    )
    assert read.status_code == 200, read.text
    assert read.json()["read"] is True
    assert _summary(platform, admin) == 1
    with platform.control() as db:
        row = db.get(BillingTransfer, uuid.UUID(submitted["id"]))
        assert row is not None and row.status == "pending_review"
    approved = platform.client.post(f"/api/v1/super-admin/billing/transfers/{submitted['id']}/approve", headers=admin)
    assert approved.status_code == 200, approved.text
    assert _summary(platform, admin) == 0
    other = _pending_invoice(platform, "bravo")
    rejected_row = _submit_for(platform, "bravo", other, "decide-transfer-2")
    assert _summary(platform, admin) == 1
    rejected = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{rejected_row['id']}/reject",
        headers=admin,
        json={"reason": "The slip is unreadable."},
    )
    assert rejected.status_code == 200, rejected.text
    assert _summary(platform, admin) == 0
    assert _notices(platform, admin)[0]["status"] == "rejected"
    reopened = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{rejected_row['id']}/reopen",
        headers=admin,
        json={"reason": "The slip is readable after all."},
    )
    assert reopened.status_code == 200, reopened.text
    assert _summary(platform, admin) == 1


def test_live_count_is_pushed_and_restored_on_reconnect(platform) -> None:  # noqa: F811
    with platform.client:
        admin = platform.operator(email="live-admin@axizpos.com")
        other = platform.operator(email="live-other@axizpos.com")
        token = admin["Authorization"].split(" ", 1)[1]
        with platform.client.websocket_connect(f"/api/v1/super-admin/billing/live?token={token}") as socket:
            hello = socket.receive_json()
            assert hello == {"type": "payment.pending_count", "pending": 0}
            invoice_id = _pending_invoice(platform)
            submitted = _submit(platform, invoice_id, "live-transfer-1")
            event = socket.receive_json()
            assert event["type"] == "payment.submitted_for_review"
            assert event["id"]
            assert event["payment_submission_id"] == submitted["id"]
            assert event["pending"] == 1
            assert event["status"] == "pending_review"
            assert "bank_reference" not in event
            assert _summary(platform, other) == 1
        with platform.client.websocket_connect(f"/api/v1/super-admin/billing/live?token={token}") as socket:
            restored = socket.receive_json()
            assert restored["pending"] == 1
        other_token = other["Authorization"].split(" ", 1)[1]
        with platform.client.websocket_connect(f"/api/v1/super-admin/billing/live?token={other_token}") as socket:
            shared = socket.receive_json()
            assert shared == {"type": "payment.pending_count", "pending": 1}
        store = platform.headers("alpha")["Authorization"].split(" ", 1)[1]
        with pytest.raises(WebSocketDisconnect):
            with platform.client.websocket_connect(f"/api/v1/super-admin/billing/live?token={store}"):
                pass


def _submit_for(host, slug: str, invoice_id: str, key: str) -> dict:
    response = host.client.post(
        "/api/v1/billing/transfers",
        headers=host.headers(slug),
        data={
            "invoice_id": invoice_id,
            "amount_fils": "14900",
            "transferred_on": "2026-10-26",
            "idempotency_key": key,
            "bank_reference": key,
        },
        files={"receipt": ("pay.png", PNG, "image/png")},
    )
    assert response.status_code == 200, response.text
    return response.json()
