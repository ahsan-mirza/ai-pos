"""Queues a posted sale or refund for the e-Invoicing plugin without changing VAT.

The insert shares the caller's transaction through a savepoint. A missing plugin table
cannot roll back the sale. B2C receipts are not queued.
"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability

log = logging.getLogger("ai-pos.einvoicing")
_PLUGIN = Path(__file__).resolve().parents[4] / "plugins" / "einvoicing"
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))


def _insert(db: Session, tenant_id: uuid.UUID, kind: str, source_id: uuid.UUID) -> None:
    from einvoicing.models import Outbox

    nested = db.begin_nested()
    try:
        db.add(
            Outbox(
                tenant_id=tenant_id,
                kind=kind,
                source_id=source_id,
                status="PENDING",
                attempts=0,
                last_error="",
            )
        )
        db.flush()
        nested.commit()
    except Exception:
        nested.rollback()
        log.warning("e-Invoicing outbox was not written for %s %s", kind, source_id)


def note_sale(db: Session, *, tenant_id: uuid.UUID, sale_id: uuid.UUID, buyer_trn: str | None) -> None:
    if not (buyer_trn or "").strip():
        return
    if not has_capability(db, Capability.UAE_EINVOICING):
        return
    _insert(db, tenant_id, "sale", sale_id)


def note_return(db: Session, *, tenant_id: uuid.UUID, return_id: uuid.UUID) -> None:
    if not has_capability(db, Capability.UAE_EINVOICING):
        return
    _insert(db, tenant_id, "return", return_id)
