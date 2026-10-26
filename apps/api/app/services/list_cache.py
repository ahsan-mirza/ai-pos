"""Cache-aside for tenant-scoped list responses.

The key includes the tenant and a resource version. Mutations increment the version, so the next read
misses without flushing another tenant's entries. Redis errors fall through to the loader.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable

from app.core import cache
from app.tenancy.context import current_tenant

log = logging.getLogger(__name__)


def _tenant_id() -> str:
    tenant = current_tenant()
    return tenant.id if tenant is not None else "local"


def _version_key(resource: str) -> str:
    return f"listver:{_tenant_id()}:{resource}"


def bump(resource: str) -> None:
    """Drops this tenant's cached pages for one list. Other tenants keep their entries."""
    cache.increment(_version_key(resource))


def remember[T](resource: str, fingerprint: str, ttl_seconds: int, load: Callable[[], T]) -> T:
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    version = cache.get_value(_version_key(resource)) or "0"
    key = f"list:{_tenant_id()}:{resource}:{version}:{digest}"
    cached = _read(key)
    if cached is not None:
        return cached
    if not cache.claim(f"lock:{key}", 2):
        cached = _read(key)
        if cached is not None:
            return cached
    value = load()
    cache.set_value(key, json.dumps(value, default=str), ttl_seconds)
    return value


def _read(key: str) -> object | None:
    raw = cache.get_value(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning("list cache entry was not json")
        return None
