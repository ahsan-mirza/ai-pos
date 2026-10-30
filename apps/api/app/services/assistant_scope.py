"""Tenant scope for the assistant. The model never supplies the tenant, the branch, or the cache key.

Keys always start with ai:{tenant}. A missing tenant is a hard error when multi-tenant mode is on.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.core.cache import delete, get_value, set_value
from app.core.deps import Principal
from app.core.errors import ApiError

_CONVERSATION_TTL = 60 * 60 * 24 * 30


def require_tenant_id() -> str:
    """The store bound to this request. Never a value from the prompt or a tool argument."""
    from app.core.config import get_settings
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    if get_settings().tenancy_enabled:
        if tenant is None or not tenant.id:
            raise ApiError(400, "tenant_required", "This request has no store context.")
        return tenant.id
    from app.tenancy.scoping import active_tenant_id

    return str(active_tenant_id())


def _branch_part(principal: Principal) -> str:
    return str(principal.store_id) if principal.store_id is not None else "all"


def _permission_part(principal: Principal) -> str:
    names = ",".join(sorted(principal.permissions))
    return hashlib.sha256(names.encode()).hexdigest()[:12]


def report_cache_key(tenant_id: str, branch: str, principal: Principal, tool: str, args: dict[str, Any]) -> str:
    """Identity for one report. Tenant and branch come from the server, not from `args`."""
    digest = hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()[:24]
    return f"ai:{tenant_id}:{branch}:report:{tool}:{_permission_part(principal)}:{digest}"


def read_cached_report(key: str) -> str | None:
    if not key.startswith("ai:"):
        return None
    return get_value(key)


def store_cached_report(key: str, payload: str, ttl_seconds: int) -> None:
    if ttl_seconds <= 0 or not key.startswith("ai:"):
        return
    set_value(key, payload, ttl_seconds)


def invalidate_assistant_cache(tenant_id: str) -> None:
    """Drops this store's assistant cache. A Redis miss is ignored so checkout is unaffected."""
    from app.core.cache import clear_prefix

    if not tenant_id:
        return
    try:
        clear_prefix(f"ai:{tenant_id}:")
    except Exception:
        return


def _conversation_key(tenant_id: str, principal: Principal, conversation_id: uuid.UUID) -> str | None:
    if principal.user is None:
        return None
    return f"ai:{tenant_id}:{_branch_part(principal)}:{principal.user.id}:conversation:{conversation_id}"


def load_conversation(principal: Principal, conversation_id: uuid.UUID) -> list[dict[str, str]] | None:
    key = _conversation_key(require_tenant_id(), principal, conversation_id)
    if key is None:
        return None
    raw = get_value(key)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    return [
        {"role": item["role"], "content": item["content"]}
        for item in parsed
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"} and isinstance(item.get("content"), str)
    ]


def save_exchange(principal: Principal, conversation_id: uuid.UUID, question: str, answer: str) -> None:
    """Appends one turn under this user and store. Another store's id is a different key."""
    key = _conversation_key(require_tenant_id(), principal, conversation_id)
    if key is None:
        return
    current = load_conversation(principal, conversation_id) or []
    current.append({"role": "user", "content": question[:500]})
    current.append({"role": "assistant", "content": answer[:2000]})
    set_value(key, json.dumps(current[-24:]), _CONVERSATION_TTL)


def delete_conversation(principal: Principal, conversation_id: uuid.UUID) -> bool:
    key = _conversation_key(require_tenant_id(), principal, conversation_id)
    if key is None or get_value(key) is None:
        return False
    delete(key)
    return True
