"""Per-client limits for public pages (repair approval and tracking links).

The counter lives in Redis. A Redis failure refuses the request. The token is still the secret.
"""

import hashlib

from fastapi import Request

from app.core.cache import clear_prefix, hit


def check(request: Request, bucket: str, *, limit: int, window_seconds: int) -> None:
    client = request.client.host if request.client else "unknown"
    hit(f"{bucket}:{client}", limit=limit, window_seconds=window_seconds)


def check_identity(
    request: Request,
    bucket: str,
    identity: str,
    *,
    ip_limit: int,
    identity_limit: int,
    window_seconds: int,
) -> None:
    """Limits one public action by client address and by a hash of the normalized identity."""
    check(request, bucket, limit=ip_limit, window_seconds=window_seconds)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    hit(f"{bucket}:id:{digest}", limit=identity_limit, window_seconds=window_seconds)


def reset() -> None:
    clear_prefix("rate:")
