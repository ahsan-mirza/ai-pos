"""Plan-change requests record intent. Only the existing transfer approval activates the plan."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from tests.governance_support import platform  # noqa: F401

from app.console.billing import assign_free, ensure_catalog
from app.core.permissions import STORE_MANAGER_ROLE_ID
from app.core.security import hash_password
from app.models.user import User
from app.tenancy.models import (
    BillingPlan,
    PlatformBankAccount,
    Subscription,
    SubscriptionChangeEvent,
    SubscriptionChangeRequest,
    Tenant,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
FLOOR_PASSWORD = "floor-lead-test-password"


def _plan_code(host, slug: str) -> str:
    tenant_id = uuid.UUID(host.tenant_id(slug))
    with host.control() as db:
        row = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).one()
        return db.get(BillingPlan, row.plan_id).code


def _prepare(host) -> None:
    with host.control() as db:
        ensure_catalog(db)
        tenant = db.get(Tenant, uuid.UUID(host.tenant_id("alpha")))
        assign_free(db, tenant)
        if db.query(PlatformBankAccount).filter(PlatformBankAccount.active.is_(True)).first() is None:
            db.add(PlatformBankAccount(display_name="Axiz", bank_name="Test Bank", holder_name="Axiz POS"))
        db.commit()
    with host.session("alpha") as db:
        db.add(
            User(
                username="floor",
                email="floor@alpha.example",
                full_name="Floor Lead",
                hashed_password=hash_password(FLOOR_PASSWORD),
                role_id=uuid.UUID(STORE_MANAGER_ROLE_ID),
                has_portal_access=True,
                is_active=True,
            )
        )
        db.commit()


def _checkout_body(plan: str, cycle: str, total: int) -> dict:
    del total
    return {
        "plan_code": plan,
        "cycle_code": cycle,
        "addons": [],
        "hardware": [],
        "mode": "keep",
        "opening_stock": "keep",
        "confirm": "Alpha Mobiles",
        "tax_acknowledged": True,
        "payment": "transfer",
    }


def test_plan_change_waits_for_the_existing_verification_path(platform) -> None:  # noqa: F811
    _prepare(platform)
    admin = platform.headers("alpha")
    bravo = platform.headers("bravo")
    assert _plan_code(platform, "alpha") == "FREE"

    forged = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "GROWTH", "cycle_code": "MONTHLY", "tenant_id": platform.tenant_id("bravo")},
    )
    assert forged.status_code == 422

    floor = platform.client.post(
        "/api/v1/auth/login-password",
        headers={"X-Tenant-Domain": "alpha.axizpos.com"},
        json={"username": "floor", "password": FLOOR_PASSWORD},
    )
    assert floor.status_code == 200, floor.text
    employee = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers={"X-Tenant-Domain": "alpha.axizpos.com", "Authorization": f"Bearer {floor.json()['access_token']}"},
        json={"plan_code": "GROWTH", "cycle_code": "MONTHLY"},
    )
    assert employee.status_code == 403

    for plan, cycle, code in (
        ("ENTERPRISE", "MONTHLY", "custom_pricing"),
        ("LITE", "MONTHLY", "plan_not_selectable"),
        ("FREE", "ANNUAL", "nothing_to_bill"),
        ("GROWTH", "WEEKLY", "unknown_cycle"),
    ):
        denied = platform.client.post(
            "/api/v1/billing/subscription-changes",
            headers=admin,
            json={"plan_code": plan, "cycle_code": cycle},
        )
        assert denied.status_code in (404, 422), denied.text
        assert denied.json()["error"]["code"] == code

    same = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "FREE", "cycle_code": "MONTHLY"},
    )
    assert same.status_code == 409
    assert same.json()["error"]["code"] == "already_current"
    assert _plan_code(platform, "alpha") == "FREE"

    created = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "GROWTH", "cycle_code": "MONTHLY"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["status"] == "quoted"
    assert body["current_plan_code"] == "FREE"
    assert body["requested_plan_code"] == "GROWTH"
    assert body["quote"]["total_fils"] > 0
    assert body["invoice_id"] is None
    assert _plan_code(platform, "alpha") == "FREE"

    again = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "PRO_AI", "cycle_code": "MONTHLY"},
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "change_in_progress"

    listed = platform.client.get("/api/v1/billing/subscription-changes", headers=admin)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    other = platform.client.get(
        "/api/v1/billing/subscription-changes",
        headers=bravo,
        params={"tenant_id": platform.tenant_id("alpha")},
    )
    assert other.status_code == 200
    assert other.json()["items"] == []
    hidden = platform.client.get(f"/api/v1/billing/subscription-changes/{body['id']}", headers=bravo)
    assert hidden.status_code == 404
    blocked = platform.client.post(f"/api/v1/billing/subscription-changes/{body['id']}/cancel", headers=bravo)
    assert blocked.status_code == 404

    cancelled = platform.client.post(f"/api/v1/billing/subscription-changes/{body['id']}/cancel", headers=admin)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    closed = platform.client.post(f"/api/v1/billing/subscription-changes/{body['id']}/cancel", headers=admin)
    assert closed.status_code == 409

    reopened = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "GROWTH", "cycle_code": "MONTHLY"},
    )
    assert reopened.status_code == 200, reopened.text
    request_id = reopened.json()["id"]
    total = reopened.json()["quote"]["total_fils"]
    issued = platform.client.post(
        f"/api/v1/billing/subscription-changes/{request_id}/checkout",
        headers=admin,
        json=_checkout_body("GROWTH", "MONTHLY", total),
    )
    assert issued.status_code == 200, issued.text
    invoice_id = issued.json()["checkout"]["checkout_id"]
    assert issued.json()["request"]["status"] == "pending_payment"
    assert issued.json()["request"]["invoice_id"] == invoice_id
    assert _plan_code(platform, "alpha") == "FREE"
    repeat = platform.client.post(
        f"/api/v1/billing/subscription-changes/{request_id}/checkout",
        headers=admin,
        json=_checkout_body("GROWTH", "MONTHLY", total),
    )
    assert repeat.status_code == 200, repeat.text
    assert repeat.json()["checkout"]["checkout_id"] == invoice_id
    with platform.control() as db:
        tenant_id = uuid.UUID(platform.tenant_id("alpha"))
        from app.tenancy.models import BillingInvoice

        assert db.query(BillingInvoice).filter(BillingInvoice.tenant_id == tenant_id, BillingInvoice.plan_code == "GROWTH").count() == 1
    cannot = platform.client.post(f"/api/v1/billing/subscription-changes/{request_id}/cancel", headers=admin)
    assert cannot.status_code == 409

    proof = platform.client.post(
        "/api/v1/billing/transfers",
        headers=admin,
        data={
            "invoice_id": invoice_id,
            "amount_fils": str(total),
            "transferred_on": "2026-11-14",
            "idempotency_key": "plan-change-proof",
            "bank_reference": "plan-change-proof",
        },
        files={"receipt": ("pay.png", PNG, "image/png")},
    )
    assert proof.status_code == 200, proof.text
    waiting = platform.client.get(f"/api/v1/billing/subscription-changes/{request_id}", headers=admin)
    assert waiting.json()["status"] == "payment_submitted"
    assert _plan_code(platform, "alpha") == "FREE"
    store_approve = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{proof.json()['id']}/approve",
        headers=admin,
    )
    assert store_approve.status_code in (401, 403)

    operator = platform.operator(email="plan-change-admin@axizpos.com")
    approved = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{proof.json()['id']}/approve",
        headers=operator,
    )
    assert approved.status_code == 200, approved.text
    assert _plan_code(platform, "alpha") == "GROWTH"
    done = platform.client.get(f"/api/v1/billing/subscription-changes/{request_id}", headers=admin)
    assert done.json()["status"] == "completed"
    assert [event["status"] for event in done.json()["events"]].count("completed") == 1
    second = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{proof.json()['id']}/approve",
        headers=operator,
    )
    assert second.status_code == 200
    assert second.json()["id"] == approved.json()["id"]
    done_again = platform.client.get(f"/api/v1/billing/subscription-changes/{request_id}", headers=admin)
    assert [event["status"] for event in done_again.json()["events"]].count("completed") == 1
    finished = platform.client.post(f"/api/v1/billing/subscription-changes/{request_id}/cancel", headers=admin)
    assert finished.status_code == 409
    assert finished.json()["error"]["code"] == "change_completed"

    nxt = platform.client.post(
        "/api/v1/billing/subscription-changes",
        headers=admin,
        json={"plan_code": "PRO_AI", "cycle_code": "ANNUAL"},
    )
    assert nxt.status_code == 200, nxt.text
    nxt_id = nxt.json()["id"]
    nxt_total = nxt.json()["quote"]["total_fils"]
    nxt_invoice = platform.client.post(
        f"/api/v1/billing/subscription-changes/{nxt_id}/checkout",
        headers=admin,
        json=_checkout_body("PRO_AI", "ANNUAL", nxt_total),
    )
    assert nxt_invoice.status_code == 200, nxt_invoice.text
    nxt_proof = platform.client.post(
        "/api/v1/billing/transfers",
        headers=admin,
        data={
            "invoice_id": nxt_invoice.json()["checkout"]["checkout_id"],
            "amount_fils": str(nxt_total),
            "transferred_on": "2026-11-14",
            "idempotency_key": "plan-change-reject",
            "bank_reference": "plan-change-reject",
        },
        files={"receipt": ("pay.png", PNG, "image/png")},
    )
    assert nxt_proof.status_code == 200, nxt_proof.text
    rejected = platform.client.post(
        f"/api/v1/super-admin/billing/transfers/{nxt_proof.json()['id']}/reject",
        headers=operator,
        json={"reason": "The slip is unreadable."},
    )
    assert rejected.status_code == 200, rejected.text
    after = platform.client.get(f"/api/v1/billing/subscription-changes/{nxt_id}", headers=admin)
    assert after.json()["status"] == "pending_payment"
    assert after.json()["rejection_reason"] == "The slip is unreadable."
    assert _plan_code(platform, "alpha") == "GROWTH"


def test_one_open_request_is_enforced_by_the_database(platform) -> None:  # noqa: F811
    tenant_id = uuid.UUID(platform.tenant_id("alpha"))
    with platform.control() as db:
        first = SubscriptionChangeRequest(
            tenant_id=tenant_id,
            reference="SCR-ONE",
            current_plan_code="FREE",
            requested_plan_code="GROWTH",
            requested_cycle_code="MONTHLY",
            status="quoted",
            quote_snapshot={"currency": "AED", "total_fils": 1},
            correlation_id=uuid.uuid4(),
        )
        db.add(first)
        db.commit()
        db.add(
            SubscriptionChangeRequest(
                tenant_id=tenant_id,
                reference="SCR-TWO",
                current_plan_code="FREE",
                requested_plan_code="PRO_AI",
                requested_cycle_code="MONTHLY",
                status="pending_payment",
                quote_snapshot={"currency": "AED", "total_fils": 1},
                correlation_id=uuid.uuid4(),
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
        first_row = db.query(SubscriptionChangeRequest).filter(SubscriptionChangeRequest.reference == "SCR-ONE").one()
        first_row.status = "cancelled"
        db.commit()
        db.add(
            SubscriptionChangeRequest(
                tenant_id=tenant_id,
                reference="SCR-TWO",
                current_plan_code="FREE",
                requested_plan_code="PRO_AI",
                requested_cycle_code="MONTHLY",
                status="quoted",
                quote_snapshot={"currency": "AED", "total_fils": 1},
                correlation_id=uuid.uuid4(),
            )
        )
        db.commit()
        assert db.query(SubscriptionChangeRequest).filter(SubscriptionChangeRequest.tenant_id == tenant_id).count() == 2
        completed = db.query(SubscriptionChangeRequest).filter(SubscriptionChangeRequest.reference == "SCR-TWO").one()
        db.add(
            SubscriptionChangeEvent(
                request_id=completed.id,
                previous_status="payment_submitted",
                status="completed",
                actor_type="console",
                correlation_id=completed.correlation_id,
            )
        )
        db.commit()
        db.add(
            SubscriptionChangeEvent(
                request_id=completed.id,
                previous_status="payment_submitted",
                status="completed",
                actor_type="console",
                correlation_id=completed.correlation_id,
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
