from datetime import datetime
from typing import Literal
from uuid import UUID

from app.schemas.payloads import ApiModel, SerialKind

SerialStatus = Literal[
    "registered", "received", "in_stock", "reserved", "in_transit", "sold", "defective", "repair", "quarantine",
    "scrapped", "reversed",
]  # fmt: skip


class SerialSearchRow(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str | None
    sku: str | None
    store_id: UUID
    store_code: str
    kind: SerialKind
    # The full IMEI/serial for registers and stock managers; "•••• 1234" for everyone else.
    value: str
    last4: str
    status: str
    batch_number: str | None
    # Only for portal users who manage inventory or read reports.
    purchase_cost_cents: int | None
    created_at: datetime
    updated_at: datetime


class SerialSearchOut(ApiModel):
    # exact: matched a full identifier; suffix: its last characters; all: no query; none: the query is unusable.
    match: Literal["exact", "suffix", "all", "none"]
    rows: list[SerialSearchRow]
    hint: str | None
