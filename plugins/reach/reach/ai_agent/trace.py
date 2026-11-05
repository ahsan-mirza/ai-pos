"""Structured customer-care logs. Message text, keys, and webhook secrets stay out."""

from __future__ import annotations

import logging

logger = logging.getLogger("ai_pos.reach.ai")

_HIDDEN = frozenset({"body", "text", "content", "api_key", "authorization", "secret", "token", "password"})


def trace(stage: str, **fields: object) -> None:
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    parts = [f"stage={stage}", f"tenant_id={'' if tenant is None else tenant.id}"]
    for key in sorted(fields):
        if key in _HIDDEN or fields[key] is None:
            continue
        parts.append(f"{key}={fields[key]}")
    logger.info("[AXIZREACH_AI] %s", " ".join(parts))
