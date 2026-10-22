"""Demand forecasts for replenishment. Small, explainable models picked per product by backtest:

- weighted average: 50% last 7 days, 30% last 28, 20% last 90 (the original replenishment rate),
- trend: Holt's linear exponential smoothing, for products that are growing or fading,
- weekly: the weighted average shaped by the product's day-of-week profile (weekend peaks),
- trend + weekly: both.

Each method is fitted on all but the last 28 days and scored on those 28 (WAPE: total absolute error over total
units). The lowest error wins; products with too little history keep the weighted average."""

from dataclasses import dataclass
from datetime import date, timedelta

BACKTEST_DAYS = 28
MIN_UNITS_FOR_MODELS = 12
METHODS = ("weighted_average", "trend", "weekly", "trend_weekly")
METHOD_LABELS = {
    "weighted_average": "Weighted average",
    "trend": "Trend",
    "weekly": "Weekday pattern",
    "trend_weekly": "Trend + weekday pattern",
}


@dataclass(frozen=True)
class Forecast:
    method: str
    #: Units per day for each day of the horizon, starting the day after `history` ends.
    daily: tuple[float, ...]
    #: 1 - WAPE on the backtest, 0-1; None when there was too little history to test.
    accuracy: float | None
    #: Holt trend as % change per week of the current level; None for non-trend methods.
    trend_pct_week: float | None

    @property
    def total(self) -> float:
        return sum(self.daily)

    @property
    def rate(self) -> float:
        return self.total / len(self.daily) if self.daily else 0.0


def weighted_average(history: list[int]) -> float:
    def mean(window: int) -> float:
        window = min(window, len(history)) or 1
        return sum(history[-window:]) / window

    return 0.5 * mean(7) + 0.3 * mean(28) + 0.2 * mean(len(history))


def holt(history: list[int], alpha: float = 0.3, beta: float = 0.1) -> tuple[float, float]:
    """Level and per-day trend after smoothing the whole series."""
    if not history:
        return 0.0, 0.0
    level, trend = float(history[0]), 0.0
    for value in history[1:]:
        previous = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - previous) + (1 - beta) * trend
    return level, trend


def weekday_profile(history: list[int], last_day: date, weeks: int = 8, shrink: float = 2.0) -> list[float]:
    """Multiplier per weekday (Mon=0) from the last `weeks` weeks, pulled toward 1 when evidence is thin."""
    window = history[-weeks * 7 :]
    if not window or sum(window) == 0:
        return [1.0] * 7
    overall = sum(window) / len(window)
    sums = [0.0] * 7
    counts = [0] * 7
    start = last_day - timedelta(days=len(window) - 1)
    for offset, value in enumerate(window):
        weekday = (start + timedelta(days=offset)).weekday()
        sums[weekday] += value
        counts[weekday] += 1
    profile = []
    for weekday in range(7):
        raw = (sums[weekday] / counts[weekday]) / overall if counts[weekday] else 1.0
        profile.append((counts[weekday] * raw + shrink) / (counts[weekday] + shrink))
    mean = sum(profile) / 7
    return [value / mean for value in profile]


def _project(method: str, history: list[int], last_day: date, horizon: int) -> tuple[list[float], float | None]:
    weekly = method in ("weekly", "trend_weekly")
    profile = weekday_profile(history, last_day) if weekly else [1.0] * 7
    if method in ("trend", "trend_weekly"):
        level, trend = holt(history)
        base = [max(0.0, level + trend * step) for step in range(1, horizon + 1)]
        trend_pct = (trend * 7 / level * 100) if level > 0 else 0.0
    else:
        rate = weighted_average(history)
        base = [rate] * horizon
        trend_pct = None
    daily = [base[step] * profile[(last_day + timedelta(days=step + 1)).weekday()] for step in range(horizon)]
    return daily, trend_pct


def wape(actual: list[int], predicted: list[float]) -> float:
    total = sum(actual)
    error = sum(abs(a - p) for a, p in zip(actual, predicted, strict=True))
    if total == 0:
        return 0.0 if error < 0.5 else 1.0
    return error / total


def forecast(history: list[int], last_day: date, horizon: int) -> Forecast:
    """`history` is units per day, oldest first, ending on `last_day`."""
    horizon = max(horizon, 1)
    if sum(history) < MIN_UNITS_FOR_MODELS or len(history) < BACKTEST_DAYS * 2:
        daily, _ = _project("weighted_average", history, last_day, horizon)
        return Forecast("weighted_average", tuple(daily), None, None)
    train, test = history[:-BACKTEST_DAYS], history[-BACKTEST_DAYS:]
    train_end = last_day - timedelta(days=BACKTEST_DAYS)
    errors = {}
    for method in METHODS:
        predicted, _ = _project(method, train, train_end, BACKTEST_DAYS)
        errors[method] = wape(test, predicted)
    # Simpler methods win ties: a model has to beat the weighted average clearly to be used.
    best = min(METHODS, key=lambda method: (round(errors[method], 2), METHODS.index(method)))
    if errors[best] > errors["weighted_average"] - 0.02:
        best = "weighted_average"
    daily, trend_pct = _project(best, history, last_day, horizon)
    return Forecast(best, tuple(daily), max(0.0, 1 - errors[best]), trend_pct)
