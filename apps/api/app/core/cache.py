"""Redis for tenant-scoped cache and rate limits. Stock and payments stay in PostgreSQL.

A missing Redis URL uses an in-process fake outside production, so tests and a laptop still boot.
Cache reads miss when Redis is down. Rate limits refuse the request instead of guessing.
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.errors import ApiError

log = logging.getLogger("ai_pos.cache")

_client = None
_url: str | None = None


def _client_for():
    global _client, _url
    settings = get_settings()
    url = settings.redis_url or ""
    if _client is not None and _url == url:
        return _client
    if url:
        import redis

        _client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=0.5)
    else:
        import fakeredis

        _client = fakeredis.FakeRedis(decode_responses=True)
    _url = url
    return _client


def reset() -> None:
    """Drops the process-local client. Tests call this between cases."""
    global _client, _url
    _client = None
    _url = None


def get_value(key: str) -> str | None:
    try:
        return _client_for().get(key)
    except RedisError:
        log.warning("cache read failed")
        return None


def set_value(key: str, value: str, ttl_seconds: int) -> None:
    try:
        _client_for().set(key, value, ex=ttl_seconds)
    except RedisError:
        log.warning("cache write failed")


def delete(key: str) -> None:
    try:
        _client_for().delete(key)
    except RedisError:
        log.warning("cache delete failed")


def hit(key: str, *, limit: int, window_seconds: int) -> None:
    """Counts one hit. Raises 429 when the window is full, and 503 when Redis cannot be reached."""
    scoped = f"rate:{key}"
    try:
        client = _client_for()
        count = int(client.incr(scoped))
        if count == 1:
            client.expire(scoped, window_seconds)
    except RedisError as exc:
        raise ApiError(503, "unavailable", "Try again in a moment.") from exc
    if count > limit:
        raise ApiError(429, "rate_limited", "Too many requests. Wait a few minutes and try again.")


def clear_prefix(prefix: str) -> None:
    try:
        client = _client_for()
        for key in client.scan_iter(f"{prefix}*"):
            client.delete(key)
    except RedisError:
        log.warning("cache clear failed")
