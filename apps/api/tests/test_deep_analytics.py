"""Deep Analytics uses the management P&L figures and stays inside the caller's branch."""

import uuid
from datetime import date

import pytest
from sqlalchemy import select
from tests.test_management_reports import scenario

from app.core import capabilities as catalog
from app.core.cache import get_value, reset, set_value
from app.core.errors import ApiError
from app.models import AuditLog
from app.routers.v1.deep_analytics import _cache_key, scoped_store
from app.services.deep_analytics import forecast_from_daily, growth_bps, margin_bps


def _enable(client, headers: dict[str, str]) -> None:
    modules = [capability.value for capability in catalog.ELECTRONICS_WHOLESALE] + ["deep_analytics"]
    response = client.put(
        "/api/v1/settings/profile",
        headers=headers,
        json={"business_profile": "electronics_wholesale", "capabilities": modules},
    )
    assert response.status_code == 200, response.text


def test_margin_and_forecast_rules() -> None:
    assert margin_bps(3600, 6000) == 6000
    assert margin_bps(1, 0) is None
    assert growth_bps(150, 100) == 5000
    assert growth_bps(10, 0) is None
    short = forecast_from_daily([100] * 13)
    assert short.status == "insufficient_history" and short.daily_revenue_cents is None
    ready = forecast_from_daily([100] * 14)
    assert ready.status == "estimated" and ready.daily_revenue_cents == 100


def test_a_branch_user_cannot_ask_for_another_branch() -> None:
    home = uuid.uuid4()
    other = uuid.uuid4()

    class Caller:
        store_id = home

    with pytest.raises(ApiError) as caught:
        scoped_store(Caller(), other)
    assert caught.value.status_code == 403 and caught.value.code == "store_forbidden"
    assert scoped_store(Caller(), None) == home
    assert scoped_store(Caller(), home) == home


def test_cache_identity_includes_the_tenant(monkeypatch) -> None:
    reset()
    first = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
    second = uuid.UUID("00000000-0000-4000-8000-0000000000b2")
    monkeypatch.setattr("app.routers.v1.deep_analytics.active_tenant_id", lambda: first)
    own = _cache_key(None, date(2026, 10, 1), date(2026, 10, 29), "AED", False)
    monkeypatch.setattr("app.routers.v1.deep_analytics.active_tenant_id", lambda: second)
    other = _cache_key(None, date(2026, 10, 1), date(2026, 10, 29), "AED", False)
    set_value(own, '{"currency":"AED"}', 30)
    assert get_value(other) is None
    assert own != other


def test_overview_matches_the_management_profit(client, session) -> None:
    headers = scenario(client, session)
    period = {"from": "2026-10-19", "to": "2026-10-19"}
    blocked = client.get("/api/v1/deep-analytics/overview", headers=headers, params=period)
    assert blocked.status_code == 403

    _enable(client, headers)
    report = client.get("/api/v1/deep-analytics/overview", headers=headers, params=period)
    assert report.status_code == 200, report.text
    body = report.json()
    figures = {row["key"]: row for row in body["kpis"]}
    assert figures["net_sales"]["cents"] == 6000
    assert figures["cogs"]["cents"] == 2400
    assert figures["gross_profit"]["cents"] == 3600
    assert figures["gross_margin"]["bps"] == 6000
    assert figures["transactions"]["count"] == 1
    assert figures["refunds"]["cents"] == 0
    assert body["forecast"]["status"] == "insufficient_history"
    assert body["products"][0]["name"] == "USB-C Cable"
    assert {section["id"] for section in body["sections"]} >= {"serials", "wholesale"}
    assert "kitchen" not in {section["id"] for section in body["sections"]}

    exported = client.get("/api/v1/deep-analytics/export", headers=headers, params=period)
    assert exported.status_code == 200 and "net_sales,6000,exact" in exported.text
    session.expire_all()
    logged = session.scalar(select(AuditLog).where(AuditLog.action == "export.deep_analytics"))
    assert logged is not None


def test_deep_analytics_is_optional_for_every_business_type() -> None:
    for profile in catalog.PROFILES:
        optional = {capability.value for capability in catalog.catalogue(profile).optional}
        preset = {capability.value for capability in catalog.PROFILES[profile]}
        assert "deep_analytics" in optional
        assert "deep_analytics" not in preset
