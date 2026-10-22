from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SerialNumber(TimestampMixin, Base):
    __tablename__ = "serial_numbers"
    __table_args__ = (Index("ix_serial_numbers_product_store_status", "product_id", "store_id", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    value_hash: Mapped[str] = mapped_column(String(64), unique=True)
    value_encrypted: Mapped[str] = mapped_column(Text)
    # Last characters in plain text for "ends with" search; null until backfilled for rows made before it existed.
    value_suffix: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    # The purchase batch line that brought this unit in; selling it draws from that batch, not FIFO.
    batch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batch_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
