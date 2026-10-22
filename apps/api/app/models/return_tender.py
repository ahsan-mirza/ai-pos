from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.store_credit import StoreCredit

if TYPE_CHECKING:
    from app.models.sale_return import SaleReturn


class ReturnTender(Base):
    __tablename__ = "return_tenders"
    __table_args__ = (CheckConstraint("amount_cents >= 1", name="amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    return_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("returns.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(Integer)
    store_credit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("store_credits.id"),
        nullable=True,
    )
    sale_return: Mapped[SaleReturn] = relationship("SaleReturn", back_populates="tenders")
    store_credit: Mapped[StoreCredit | None] = relationship()
