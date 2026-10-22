import json
from pathlib import Path

import pytest

from app.services.pricing import effective_tier, resolve_price, resolve_with_lists

FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "fixtures"
DATA = json.loads((FIXTURES / "pricing-cases.json").read_text(encoding="utf-8"))
LISTS = json.loads((FIXTURES / "price-list-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", LISTS["cases"], ids=[case["name"] for case in LISTS["cases"]])
def test_price_lists_match_shared_fixture(case: dict) -> None:
    result = resolve_with_lists(
        LISTS["retail_cents"],
        LISTS["prices"],
        case["tier"],
        case["pieces"],
        LISTS["entries"],
        customer_id=case["customer_id"],
        group_id=case["group_id"],
        store_id=case["store_id"],
        at=case["at"],
    )
    assert (result.price_cents, result.source, result.price_list_id) == (
        case["price_cents"],
        case["source"],
        case["price_list_id"],
    )
    assert case["price_cents"] in result.candidates


@pytest.mark.parametrize("case", DATA["cases"], ids=[case["name"] for case in DATA["cases"]])
def test_resolve_price_matches_shared_fixture(case: dict) -> None:
    result = resolve_price(DATA["retail_cents"], DATA["prices"], case["tier"], case["pieces"])
    assert result.price_cents == case["price_cents"]
    assert result.tier == case["resolved_tier"]
    assert result.source == case["source"]
    assert result.moq_shortfall == case["moq_shortfall"]


def test_no_tier_rows_is_retail() -> None:
    result = resolve_price(2000, [], "DISTRIBUTOR", 500)
    assert (result.price_cents, result.tier, result.source) == (2000, "RETAIL", "retail")


def test_effective_tier() -> None:
    assert effective_tier("RETAIL", "DISTRIBUTOR") == "RETAIL"
    assert effective_tier("WHOLESALE", None) == "TIER_1"
    assert effective_tier("WHOLESALE", "TIER_2") == "TIER_2"
