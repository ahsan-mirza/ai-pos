"""Document numbers. Every number is {prefix}-{NNNNNN}; a prefix is one series. Registers own one series per
device and document type so they can number tax invoices offline; the API owns the store-level series for
documents it creates. Numbers are unique business-wide; gaps and out-of-order arrivals are counted, not refused,
because an offline register's sale has already been handed to the customer."""

import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import SyncRejected
from app.models.device import Device
from app.models.document_sequence import DocumentSequence
from app.models.store import Store

SERVER_SUFFIX = {
    "INV": "S",
    "QUO": "QUO",
    "CN": "CN",
    "Z": "Z",
    "PDC": "PDC",
    "CNT": "CNT",
    "EXP": "EXP",
    "TRD": "TRD",
    # Wholesale fulfilment: sales orders, pick lists, delivery notes.
    "SO": "SO",
    "PCK": "PCK",
    "DN": "DN",
}
DEVICE_SUFFIX = {"INV": "", "CN": "-CN", "Z": "-Z", "QUO": "-QUO", "PDC": "-PDC"}
NUMBER = re.compile(r"^(?P<prefix>[A-Z0-9][A-Z0-9-]{0,38}?)-(?P<value>\d{1,9})$")


def series_code(code: str) -> str:
    return "-".join(re.findall(r"[A-Z0-9]+", code.upper())) or "STORE"


def format_number(prefix: str, value: int) -> str:
    return f"{prefix}-{value:06d}"


def device_prefix(store: Store, device: Device, doc_type: str) -> str:
    return f"{series_code(store.code)}-{series_code(device.code)}{DEVICE_SUFFIX[doc_type]}"


def _locked(db: Session, statement):  # type: ignore[no-untyped-def]
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    return statement


def _series(
    db: Session, *, prefix: str, store_id: uuid.UUID, device_id: uuid.UUID | None, doc_type: str
) -> DocumentSequence:
    row = db.scalar(_locked(db, select(DocumentSequence).where(DocumentSequence.prefix == prefix)))
    if row is None:
        row = DocumentSequence(store_id=store_id, device_id=device_id, doc_type=doc_type, prefix=prefix, last_value=0)
        db.add(row)
        db.flush()
    return row


def next_server_number(db: Session, store_id: uuid.UUID, doc_type: str) -> str:
    store = db.get(Store, store_id)
    if store is None:
        raise SyncRejected("Store does not exist.")
    prefix = f"{series_code(store.code)}-{SERVER_SUFFIX[doc_type]}"
    row = _series(db, prefix=prefix, store_id=store_id, device_id=None, doc_type=doc_type)
    row.last_value += 1
    db.flush()
    return format_number(prefix, row.last_value)


def accept_register_number(
    db: Session,
    *,
    number: str,
    store_id: uuid.UUID,
    device: Device | None,
    doc_type: str,
    taken: bool,
) -> str:
    """Validates a number a register issued and advances its series. `taken` says the number is already used."""
    match = NUMBER.fullmatch(number)
    if match is None:
        raise SyncRejected("Document numbers look like DT-01-R01-000123.")
    if taken:
        raise SyncRejected(f"Document number {number} is already used.")
    prefix, value = match.group("prefix"), int(match.group("value"))
    if device is not None:
        store = db.get(Store, store_id)
        expected = device_prefix(store, device, doc_type) if store is not None else prefix
        if prefix != expected:
            raise SyncRejected(f"This register numbers its documents {expected}-NNNNNN.")
    row = _series(db, prefix=prefix, store_id=store_id, device_id=device.id if device else None, doc_type=doc_type)
    if row.store_id != store_id or row.doc_type != doc_type:
        raise SyncRejected(f"Series {prefix} belongs to another store or document type.")
    if device is not None and row.device_id not in (None, device.id):
        raise SyncRejected(f"Series {prefix} belongs to another register.")
    if value != row.last_value + 1:
        row.gaps += 1
    row.last_value = max(row.last_value, value)
    db.flush()
    return format_number(prefix, value)
