"""UTC clock for the sale-age check.

Production reads the current time. Tests freeze one instant so a sale dated 2026-10-19 stays inside the
30-day window on any later calendar day. The production limit itself is unchanged.
"""

from datetime import UTC, datetime

_frozen: datetime | None = None


def utcnow() -> datetime:
    if _frozen is None:
        return datetime.now(UTC)
    if _frozen.tzinfo is None or _frozen.utcoffset() is None:
        return _frozen.replace(tzinfo=UTC)
    return _frozen.astimezone(UTC)


def freeze(instant: datetime) -> None:
    global _frozen
    _frozen = instant


def reset() -> None:
    global _frozen
    _frozen = None
