"""Per-client limits for public pages (repair approval and tracking links). In-process and approximate: it slows
guessing and accidental hammering; tokens themselves carry the security."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Request

from app.core.errors import ApiError

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def check(request: Request, bucket: str, *, limit: int, window_seconds: int) -> None:
    client = request.client.host if request.client else "unknown"
    key = f"{bucket}:{client}"
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and hits[0] <= now - window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise ApiError(429, "rate_limited", "Too many requests. Wait a few minutes and try again.")
        hits.append(now)


def reset() -> None:
    with _lock:
        _hits.clear()
