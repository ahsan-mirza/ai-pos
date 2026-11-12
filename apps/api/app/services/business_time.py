"""Business-day boundaries for tenant reporting.

Instants stay in UTC. "Today" is midnight-to-midnight in the tenant's IANA timezone,
shared by every branch. ZoneInfo applies daylight-saving transitions; a fixed offset does not.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business_settings import BusinessSettings

DEFAULT_REPORTING_TIMEZONE = "Asia/Dubai"


def coerce_timezone(name: str | None) -> ZoneInfo:
    raw = (name or "").strip() or DEFAULT_REPORTING_TIMEZONE
    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError:
        return ZoneInfo(DEFAULT_REPORTING_TIMEZONE)


def require_timezone(name: str) -> str:
    raw = name.strip()
    try:
        ZoneInfo(raw)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"{raw} is not a known timezone.") from exc
    return raw


def reporting_timezone(db: Session) -> ZoneInfo:
    stored = db.scalar(select(BusinessSettings.timezone).limit(1))
    return coerce_timezone(stored if isinstance(stored, str) else None)


def local_day_start(now: datetime, zone: ZoneInfo) -> datetime:
    """UTC instant of local midnight on `now`'s business date. The next local midnight is 24h later in that zone."""
    aware = now.astimezone(UTC) if now.tzinfo is not None else now.replace(tzinfo=UTC)
    local = aware.astimezone(zone)
    start = datetime.combine(local.date(), time.min, tzinfo=zone)
    return start.astimezone(UTC)


def local_day_end(now: datetime, zone: ZoneInfo) -> datetime:
    """UTC instant of the following local midnight. DST days are 23 or 25 hours, not a fixed offset."""
    aware = now.astimezone(UTC) if now.tzinfo is not None else now.replace(tzinfo=UTC)
    local = aware.astimezone(zone)
    next_day = local.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=zone).astimezone(UTC)
