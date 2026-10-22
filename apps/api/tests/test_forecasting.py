from datetime import date, timedelta

from app.services.forecasting import forecast, wape, weekday_profile, weighted_average

LAST_DAY = date(2026, 10, 18)  # a Sunday


def weekdays(length: int) -> list[int]:
    start = LAST_DAY - timedelta(days=length - 1)
    return [(start + timedelta(days=offset)).weekday() for offset in range(length)]


def test_growing_demand_picks_the_trend_model() -> None:
    history = [2 + day // 6 for day in range(90)]
    result = forecast(history, LAST_DAY, 14)
    assert result.method in ("trend", "trend_weekly")
    assert result.trend_pct_week is not None and result.trend_pct_week > 0
    assert result.total > weighted_average(history) * 14
    assert result.accuracy is not None and result.accuracy > 0.8


def test_weekend_peaks_pick_the_weekday_model() -> None:
    history = [12 if weekday >= 5 else 2 for weekday in weekdays(90)]
    result = forecast(history, LAST_DAY, 7)
    assert result.method == "weekly"
    saturday = result.daily[5]  # 18 Oct is Sunday, so day 6 of the horizon is Saturday
    monday = result.daily[0]
    assert saturday > monday * 3
    assert abs(result.total - (5 * 2 + 2 * 12)) < 4


def test_steady_demand_keeps_the_weighted_average() -> None:
    history = ([3, 4, 5, 4, 3] * 18)[:90]  # a 5-day wobble, nothing tied to weekdays or a trend
    result = forecast(history, LAST_DAY, 10)
    assert result.method == "weighted_average"
    assert abs(result.rate - weighted_average(history)) < 1e-9


def test_sparse_history_is_not_backtested() -> None:
    history = [0] * 85 + [1, 0, 2, 0, 1]
    result = forecast(history, LAST_DAY, 7)
    assert (result.method, result.accuracy) == ("weighted_average", None)


def test_wape_and_profile_helpers() -> None:
    assert wape([10, 10], [8, 12]) == 0.2
    assert wape([0, 0], [0, 0]) == 0.0
    profile = weekday_profile([1] * 56, LAST_DAY)
    assert all(abs(value - 1) < 1e-9 for value in profile)
