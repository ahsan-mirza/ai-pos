"""Redis Bloom filters for signup identifiers that are append-only in practice.

A miss means the value has not been added since the filter was built, so an existence query can be skipped.
A hit only means the value might exist: the caller must ask PostgreSQL. A missing, stale, oversized, or
unreachable filter is unknown, and unknown always falls through to PostgreSQL.

Bits are never cleared. Releasing a store address marks that filter stale so the next check rebuilds it
from the database instead of trusting an old hit. Emails and phone numbers stay on the signup row, so
those filters do not need a deletion path. Registration still enforces the unique constraints.
"""

from __future__ import annotations

import hashlib
import logging
import math
from typing import Literal

from app.core import cache

log = logging.getLogger("ai_pos.availability")

CAPACITY = 50_000
FALSE_POSITIVE_RATE = 0.01
BIT_COUNT = math.ceil(-(CAPACITY * math.log(FALSE_POSITIVE_RATE)) / (math.log(2) ** 2))
HASHES = max(1, round((BIT_COUNT / CAPACITY) * math.log(2)))

Probe = Literal["absent", "possible", "unknown"]
_READY = "ready"
_STALE = "stale"
_OVER = "over"


def _meta(kind: str) -> str:
    return f"bloom:signup:{kind}:meta"


def _count(kind: str) -> str:
    return f"bloom:signup:{kind}:count"


def _bits(kind: str) -> str:
    return f"bloom:signup:{kind}:bits"


def _lock(kind: str) -> str:
    return f"bloom:signup:{kind}:lock"


def _indexes(kind: str, value: str) -> list[int]:
    digest = hashlib.sha256(f"{kind}\0{value}".encode()).digest()
    first = int.from_bytes(digest[:8], "big")
    second = int.from_bytes(digest[8:16], "big") or 1
    return [(first + index * second) % BIT_COUNT for index in range(HASHES)]


def is_ready(kind: str) -> bool:
    if not cache.reachable():
        return False
    if cache.get_value(_meta(kind)) != _READY:
        return False
    raw = cache.get_value(_count(kind))
    if raw is None:
        return False
    try:
        count = int(raw)
    except ValueError:
        return False
    return 0 <= count <= CAPACITY


def should_rebuild(kind: str) -> bool:
    """True when Redis is up and the filter is missing or was marked stale. An oversized filter stays on PostgreSQL."""
    if not cache.reachable():
        return False
    return cache.get_value(_meta(kind)) in (None, _STALE)


def probe(kind: str, value: str) -> Probe:
    """absent is safe to trust. possible and unknown both require the database."""
    if not is_ready(kind):
        return "unknown"
    bits = cache.get_bits(_bits(kind), _indexes(kind, value))
    if bits is None:
        return "unknown"
    if all(bits):
        return "possible"
    return "absent"


def add(kind: str, value: str) -> bool:
    """Records one value on a filter that was already built. False leaves the filter untrusted."""
    if not is_ready(kind):
        return False
    count = cache.increment(_count(kind))
    if count <= 0:
        mark_stale(kind)
        return False
    if count > CAPACITY:
        cache.set_permanent(_meta(kind), _OVER)
        log.warning("bloom filter over capacity kind=%s count=%s", kind, count)
        return False
    if not cache.set_bits(_bits(kind), _indexes(kind, value)):
        mark_stale(kind)
        return False
    return True


def rebuild(kind: str, values: list[str]) -> bool:
    """Replaces the bitset from authoritative values. False when the rebuild did not finish."""
    unique = list(dict.fromkeys(values))
    if len(unique) > CAPACITY:
        cache.set_permanent(_meta(kind), _OVER)
        log.warning("bloom filter over capacity kind=%s count=%s", kind, len(unique))
        return False
    if not cache.try_claim(_lock(kind), 30):
        return False
    try:
        if not cache.set_permanent(_meta(kind), _STALE):
            return False
        cache.delete(_bits(kind))
        offsets: list[int] = []
        for value in unique:
            offsets.extend(_indexes(kind, value))
        if not cache.set_bits(_bits(kind), offsets):
            return False
        if not cache.set_permanent(_count(kind), str(len(unique))):
            return False
        return cache.set_permanent(_meta(kind), _READY)
    finally:
        cache.delete(_lock(kind))


def mark_stale(kind: str) -> None:
    cache.set_permanent(_meta(kind), _STALE)
    log.warning("bloom filter marked stale kind=%s", kind)


def mark_over(kind: str) -> None:
    cache.set_permanent(_meta(kind), _OVER)
