"""The internal card sandbox never settles an invoice or activates an add-on."""

import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from tests.test_commercial_payments import _db, _priced

from app.console.commercial_payments import (
    AxizPosSandboxCardProvider,
    UnconfiguredCardProvider,
    accept_sandbox_event,
    apply_sandbox_scenario,
    inquire_sandbox,
    record_cash,
    sandbox_card_allowed,
    start_plugin_payment,
    transition,
)
from app.core.errors import ApiError
from app.tenancy.models import BillingInvoice, CommercialPayment, SubscriptionItem


def _sandbox():
    return SimpleNamespace(
        app_env="test",
        payment_sandbox_enabled=True,
        payment_live_card_enabled=False,
        payment_sandbox_webhook_secret="sandbox-secret-value",
    )


def test_sandbox_stays_off_in_production_and_live_card_cannot_enable_it() -> None:
    assert sandbox_card_allowed(SimpleNamespace(app_env="production", payment_sandbox_enabled=True)) is False
    assert sandbox_card_allowed(SimpleNamespace(app_env="development", payment_live_card_enabled=True)) is False
    assert sandbox_card_allowed(SimpleNamespace(app_env="test")) is False
    assert sandbox_card_allowed(_sandbox()) is True
    with pytest.raises(ApiError) as refused:
        UnconfiguredCardProvider().create_session(
            CommercialPayment(
                tenant_id=uuid.uuid4(),
                method_code="card",
                purpose_type="PLUGIN_PURCHASE",
                purpose_ref="uae_einvoicing",
                amount_fils=1,
                currency="AED",
                idempotency_key="live-card-01",
            )
        )
    assert refused.value.code == "card_not_configured"


def test_sandbox_approval_does_not_pay_or_activate(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, _settings = _priced(db, monkeypatch)
    started = start_plugin_payment(
        db,
        _sandbox(),
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="card",
        idempotency_key="sandbox-ok-01",
        scenario="approved",
    )
    assert started["test_mode"] is True
    assert started["status"] == "SANDBOX_APPROVED"
    assert started["reference"].startswith("TEST")
    assert started["invoice_id"] is None
    assert started["provider_reference"].startswith("TEST-")
    assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0
    assert db.scalar(select(func.count()).select_from(SubscriptionItem)) == 0
    again = start_plugin_payment(
        db,
        _sandbox(),
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="card",
        idempotency_key="sandbox-ok-01",
        scenario="declined",
    )
    assert again["id"] == started["id"]
    assert again["status"] == "SANDBOX_APPROVED"


def test_decline_timeout_and_a_separate_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, _settings = _priced(db, monkeypatch)
    settings = _sandbox()
    declined = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="card",
        idempotency_key="sandbox-no-01",
        scenario="declined",
    )
    assert declined["status"] == "DECLINED"
    payment = db.get(CommercialPayment, declined["id"])
    assert payment is not None
    with pytest.raises(ApiError) as closed:
        apply_sandbox_scenario(db, payment, "approved")
    assert closed.value.code == "payment_closed"
    retry = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="card",
        idempotency_key="sandbox-no-02",
        scenario="timeout",
    )
    assert retry["status"] == "SANDBOX_UNKNOWN"
    waiting = db.get(CommercialPayment, retry["id"])
    assert waiting is not None
    inquire_sandbox(db, waiting)
    apply_sandbox_scenario(db, waiting, "approved")
    assert waiting.status == "SANDBOX_APPROVED"
    assert db.scalar(select(func.count()).select_from(BillingInvoice)) == 0
    assert db.scalar(select(func.count()).select_from(SubscriptionItem)) == 0


def test_invalid_transition_and_cash_cannot_collect_a_sandbox_payment() -> None:
    payment = CommercialPayment(
        tenant_id=uuid.uuid4(),
        method_code="card",
        purpose_type="PLUGIN_PURCHASE",
        purpose_ref="uae_einvoicing",
        amount_fils=100,
        currency="AED",
        status="DECLINED",
        environment="sandbox",
        idempotency_key="sandbox-transition",
    )
    with pytest.raises(ApiError) as invalid:
        transition(payment, "SANDBOX_APPROVED")
    assert invalid.value.code == "invalid_transition"
    payment.environment = "live"
    with pytest.raises(ApiError) as live:
        AxizPosSandboxCardProvider().create_session(payment)
    assert live.value.code == "sandbox_only"


def test_sandbox_webhook_is_signed_once_and_cannot_touch_a_live_payment(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _db()
    tenant, _settings = _priced(db, monkeypatch)
    settings = _sandbox()
    started = start_plugin_payment(
        db,
        settings,
        tenant,
        tenant.id,
        purpose_type="PLUGIN_PURCHASE",
        addon_code="uae_einvoicing",
        method_code="card",
        idempotency_key="sandbox-hook-01",
    )
    body = json.dumps(
        {
            "environment": "sandbox",
            "provider": "axizpos_test",
            "payment_id": str(started["id"]),
            "event_id": "event-sandbox-01",
            "scenario": "declined",
            "amount_fils": started["amount_fils"],
            "currency": started["currency"],
        }
    ).encode()
    stamp = str(int(datetime.now(UTC).timestamp()))
    signature = hmac.new(b"sandbox-secret-value", stamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    with pytest.raises(ApiError) as forged:
        accept_sandbox_event(db, settings, body, "deadbeef", stamp)
    assert forged.value.code == "invalid_signature"
    first = accept_sandbox_event(db, settings, body, signature, stamp)
    assert first["status"] == "DECLINED"
    with pytest.raises(ApiError) as duplicate:
        accept_sandbox_event(db, settings, body, signature, stamp)
    assert duplicate.value.code == "duplicate_event"
    live = CommercialPayment(
        tenant_id=tenant.id,
        method_code="card",
        purpose_type="PLUGIN_PURCHASE",
        purpose_ref="uae_einvoicing",
        amount_fils=started["amount_fils"],
        currency="AED",
        status="PENDING",
        environment="live",
        idempotency_key="live-hook-01",
    )
    db.add(live)
    db.commit()
    live_body = json.dumps(
        {
            "environment": "sandbox",
            "provider": "axizpos_test",
            "payment_id": str(live.id),
            "event_id": "event-sandbox-02",
            "scenario": "approved",
            "amount_fils": live.amount_fils,
            "currency": live.currency,
        }
    ).encode()
    live_stamp = str(int(datetime.now(UTC).timestamp()))
    live_signature = hmac.new(
        b"sandbox-secret-value", live_stamp.encode() + b"." + live_body, hashlib.sha256
    ).hexdigest()
    with pytest.raises(ApiError) as blocked:
        accept_sandbox_event(db, settings, live_body, live_signature, live_stamp)
    assert blocked.value.code == "sandbox_only"
    assert live.status == "PENDING"
    with pytest.raises(ApiError):
        record_cash(db, settings, started["id"], tenant.id, "CASH-100")
