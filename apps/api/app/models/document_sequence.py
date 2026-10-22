from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

DOC_TYPES = ("INV", "CN", "QUO", "Z", "PDC")


class DocumentSequence(TimestampMixin, Base):
    """One numbering series. Registers own a series per device so they can number invoices offline;
    the server owns the store-level series (device_id null) for documents it creates itself."""

    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint("prefix", name="uq_document_sequences_prefix"),
        CheckConstraint("last_value >= 0", name="last_value_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True, index=True
    )
    doc_type: Mapped[str] = mapped_column(String(4))
    prefix: Mapped[str] = mapped_column(String(40))
    last_value: Mapped[int] = mapped_column(Integer, default=0)
    # Numbers that arrived out of order or skipped ahead, for the audit trail.
    gaps: Mapped[int] = mapped_column(Integer, default=0)
