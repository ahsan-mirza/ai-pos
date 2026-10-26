from app.services.management_reports import _value, clearance_price, markdown_bps


def test_markdowns_deepen_with_idle_time_and_cap_at_half() -> None:
    assert markdown_bps("SLOW", 70, 180) == 1000
    assert markdown_bps("DEAD", 180, 180) == 2500
    assert markdown_bps("DEAD", 360, 180) == 3000
    assert markdown_bps("DEAD", 5000, 180) == 5000


def test_clearance_price_never_breaks_the_floor_or_cost() -> None:
    assert clearance_price(10_000, 4_000, None, 2500) == (7_500, 25)
    # A margin floor of 80.00 stops a 50% markdown at 80.00.
    assert clearance_price(10_000, 4_000, 8_000, 5000) == (8_000, 20)
    # Without a floor, cost is the limit.
    assert clearance_price(10_000, 9_000, None, 5000) == (9_000, 10)
    # Already at (or under) the floor: nothing to suggest.
    assert clearance_price(5_000, 6_000, None, 2500) == (None, 0)
    assert clearance_price(1_499, 0, None, 1000) == (1_300, 13)
    # A 50% markdown that the floor stops at 20% did not reach its target.
    suggested, achieved = clearance_price(10_000, 4_000, 8_000, 5000)
    assert suggested == 8_000 and achieved == 20 and achieved < 50


def test_weighed_cost_is_per_kilogram_and_missing_cost_is_not_zero() -> None:
    # 1.5 kg at 4.00 per kg is 6.00, not 1.5 kg times 4.00 with the grams left unscaled.
    value, estimated_units, estimated, missing = _value(1_500, [(1_500, 400)], None, scale=1000)
    assert (value, estimated_units, estimated, missing) == (600, 0, False, False)
    assert value * 1000 // 1_500 == 400
    # Uncovered units with no purchase cost are missing, not a free unit.
    value, estimated_units, estimated, missing = _value(5, [], None)
    assert (value, estimated_units, estimated, missing) == (0, 5, True, True)
    # A recorded zero cost is a real zero.
    value, _, estimated, missing = _value(5, [], 0)
    assert (value, estimated, missing) == (0, True, False)
