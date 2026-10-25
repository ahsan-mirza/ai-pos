"""Per-client limits for public pages (repair approval and tracking links).

The counter lives in Redis. A Redis failure refuses the request. The token is still the secret.
"""

from fastapi import Request

from app.core.cache import clear_prefix, hit


def check(request: Request, bucket: str, *, limit: int, window_seconds: int) -> None:
    client = request.client.host if request.client else "unknown"
    hit(f"{bucket}:{client}", limit=limit, window_seconds=window_seconds)


def reset() -> None:
    clear_prefix("rate:")
