"""The marketing site's WhatsApp button is console-managed and public reads stay narrow."""

import time

import pytest
from sqlalchemy import select
from tests.governance_support import platform  # noqa: F401

from app.console import site
from app.console.security import OperatorPrincipal
from app.console.site import normalize_email, normalize_message, normalize_tooltip, normalize_whatsapp
from app.core.errors import ApiError
from app.schemas.site import SiteContactIn, SiteContactOut
from app.tenancy.models import WHATSAPP_MESSAGE_DEFAULT, Operator, SiteSettings

PUBLIC = "/api/v1/site/contact"
ADMIN = "/api/v1/super-admin/site/contact"
PUBLIC_KEYS = {"enabled", "whatsapp", "message", "tooltip", "email"}


def test_whatsapp_fields_are_normalized() -> None:
    assert normalize_whatsapp("+971 (50) 123-4567") == "971501234567"
    assert normalize_whatsapp("") == ""
    with pytest.raises(ApiError) as short:
        normalize_whatsapp("12345")
    assert short.value.code == "invalid_whatsapp"
    with pytest.raises(ApiError) as control:
        normalize_message("hello\x00there")
    assert control.value.code == "invalid_whatsapp_message"
    assert normalize_tooltip("   ") == "Chat with Sales"
    assert normalize_tooltip("  Talk   to sales ") == "Talk to sales"
    assert normalize_email("  sales@axizpos.com ") == "sales@axizpos.com"
    assert normalize_email("") == ""
    with pytest.raises(ApiError) as email:
        normalize_email("not-an-email")
    assert email.value.code == "invalid_sales_email"


def test_only_an_admin_can_publish_the_sales_number(platform) -> None:  # noqa: F811
    site.invalidate_contact_cache()
    admin = platform.operator()
    support = platform.operator(email="desk@axizpos.com", role="SUPPORT")
    payload = {
        "enabled": True,
        "whatsapp": "+971 (50) 123-4567",
        "message": "Hello & welcome?\nThanks",
        "tooltip": "Chat with Sales",
        "email": "sales@axizpos.com",
        "reason": "Publish the sales line",
    }
    anonymous = platform.client.patch(ADMIN, json=payload)
    assert anonymous.status_code == 401
    forbidden = platform.client.patch(ADMIN, headers=support, json=payload)
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "forbidden"
    extra = platform.client.patch(ADMIN, headers=admin, json={**payload, "password": "nope"})
    assert extra.status_code == 422

    saved = platform.client.patch(ADMIN, headers=admin, json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json() == {
        "enabled": True,
        "whatsapp": "971501234567",
        "message": "Hello & welcome?\nThanks",
        "tooltip": "Chat with Sales",
        "email": "sales@axizpos.com",
    }
    assert set(saved.json()) == PUBLIC_KEYS

    public = platform.client.get(PUBLIC)
    assert public.status_code == 200, public.text
    assert public.headers["cache-control"] == "no-cache"
    assert public.json() == saved.json()
    assert "password" not in public.json() and "reason" not in public.json()

    hidden = platform.client.patch(
        ADMIN,
        headers=admin,
        json={**payload, "enabled": False, "reason": "Hide the button"},
    )
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["enabled"] is False and hidden.json()["whatsapp"] == "971501234567"
    missing = platform.client.patch(
        ADMIN,
        headers=admin,
        json={**payload, "whatsapp": "", "reason": "Turn the button on"},
    )
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "whatsapp_required"

    reloaded = platform.client.get(ADMIN, headers=admin)
    assert reloaded.json()["enabled"] is False and reloaded.json()["message"] == "Hello & welcome?\nThanks"


def test_public_contact_cache_drops_on_save_and_expires(platform, monkeypatch) -> None:  # noqa: F811
    site.invalidate_contact_cache()
    admin = platform.operator(email="cache@axizpos.com")
    first = platform.client.get(PUBLIC)
    assert first.status_code == 200 and first.json()["message"] == WHATSAPP_MESSAGE_DEFAULT
    real_read = site.read_contact

    def boom(_db):
        raise AssertionError("public contact should be cached")

    monkeypatch.setattr(site, "read_contact", boom)
    assert platform.client.get(PUBLIC).status_code == 200
    monkeypatch.setattr(site, "read_contact", real_read)

    saved = platform.client.patch(
        ADMIN,
        headers=admin,
        json={
            "enabled": True,
            "whatsapp": "+971501112233",
            "message": WHATSAPP_MESSAGE_DEFAULT,
            "tooltip": "Chat with Sales",
            "reason": "Point the button at sales",
        },
    )
    assert saved.status_code == 200, saved.text
    assert platform.client.get(PUBLIC).json()["whatsapp"] == "971501112233"

    with platform.control() as db:
        row = db.get(SiteSettings, 1)
        assert row is not None
        row.whatsapp = "971509998877"
        db.commit()
    assert platform.client.get(PUBLIC).json()["whatsapp"] == "971509998877"

    stale = SiteContactOut(enabled=True, whatsapp="971500000000", message="stale", tooltip="Chat with Sales", email="")
    with platform.control() as db:
        site.remember_contact(db, stale)
    assert platform.client.get(PUBLIC).json()["whatsapp"] == "971500000000"
    later = time.monotonic() + site.CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(site.time, "monotonic", lambda: later)
    assert platform.client.get(PUBLIC).json()["whatsapp"] == "971509998877"


def test_partial_update_keeps_fields_the_request_left_out(platform) -> None:  # noqa: F811
    site.invalidate_contact_cache()
    platform.operator()
    with platform.control() as db:
        operator = db.scalar(select(Operator).where(Operator.email == "it@axizpos.com"))
        assert operator is not None
        principal = OperatorPrincipal(
            id=operator.id, email=operator.email, full_name=operator.full_name, role=operator.role, ip=None
        )
        saved = site.set_contact(
            db,
            principal,
            SiteContactIn(
                whatsapp="+971501234567",
                message="Keep me",
                tooltip="Ask sales",
                email="sales@axizpos.com",
                reason="First publish",
            ),
        )
        assert saved.message == "Keep me" and saved.tooltip == "Ask sales" and saved.email == "sales@axizpos.com"
        updated = site.set_contact(db, principal, SiteContactIn(whatsapp="+971507654321", reason="New number"))
        assert updated.whatsapp == "971507654321"
        assert updated.message == "Keep me" and updated.tooltip == "Ask sales" and updated.enabled is True
        assert updated.email == "sales@axizpos.com"
