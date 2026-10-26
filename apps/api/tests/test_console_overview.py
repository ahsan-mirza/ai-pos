"""Overview figures come from tenants and subscriptions. An empty catalog has no invented MRR."""

from tests.governance_support import platform  # noqa: F401

from app.console.billing import _monthly_equivalent


def test_monthly_equivalent_matches_the_billed_cycle() -> None:
    assert _monthly_equivalent(14_900, 1, 0) == 14_900
    assert _monthly_equivalent(14_900, 12, 0) == 14_900
    assert _monthly_equivalent(10_000, 12, 1_000) == 9_000


def test_overview_counts_tenants_and_leaves_mrr_at_zero_without_payers(platform) -> None:  # noqa: F811
    reply = platform.client.get("/api/v1/super-admin/overview", headers=platform.operator())
    assert reply.status_code == 200, reply.text
    body = reply.json()
    assert body["tenants"] >= 1
    assert body["paying_subscriptions"] == 0
    assert body["mrr_fils"] == 0
    assert body["arr_fils"] == 0
    assert any("Trials are excluded" in line for line in body["definitions"])
