"""Business-day boundaries stay on the tenant clock, including daylight-saving days."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.business_time import local_day_end, local_day_start


def test_midnight_is_the_local_date_not_utc() -> None:
    tokyo = ZoneInfo("Asia/Tokyo")
    los_angeles = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 11, 12, 20, 30, tzinfo=UTC)
    # Tokyo is already 13 November; Los Angeles is still 12 November.
    assert local_day_start(now, tokyo) == datetime(2026, 11, 12, 15, 0, tzinfo=UTC)
    assert local_day_start(now, los_angeles) == datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
    instant = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    assert instant < local_day_start(now, tokyo)
    assert instant >= local_day_start(now, los_angeles)


def test_dubai_has_no_dst_and_midnight_is_20_utc() -> None:
    dubai = ZoneInfo("Asia/Dubai")
    # 00:30 on the 13th in Dubai is 20:30 UTC on the 12th.
    now = datetime(2026, 11, 12, 20, 30, tzinfo=UTC)
    assert local_day_start(now, dubai) == datetime(2026, 11, 12, 20, 0, tzinfo=UTC)
    assert local_day_end(now, dubai) - local_day_start(now, dubai) == timedelta(hours=24)
    just_before = datetime(2026, 11, 12, 19, 59, tzinfo=UTC)
    assert local_day_start(just_before, dubai) == datetime(2026, 11, 11, 20, 0, tzinfo=UTC)


def test_new_york_spring_forward_is_a_23_hour_business_day() -> None:
    zone = ZoneInfo("America/New_York")
    # Noon on the short day, after 02:00 becomes 03:00.
    now = datetime(2026, 3, 8, 16, 0, tzinfo=UTC)
    assert local_day_end(now, zone) - local_day_start(now, zone) == timedelta(hours=23)


def test_new_york_fall_back_is_a_25_hour_business_day() -> None:
    zone = ZoneInfo("America/New_York")
    now = datetime(2026, 11, 1, 16, 0, tzinfo=UTC)
    assert local_day_end(now, zone) - local_day_start(now, zone) == timedelta(hours=25)
