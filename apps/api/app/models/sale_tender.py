from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped

if TYPE_CHECKING:
    from app.models.sale import Sale


class SaleTender(TenantScoped, Base):
    """One payment leg of a sale. on_account legs are the portion booked to the customer's ledger."""

    __tablename__ = "sale_tenders"
    __table_args__ = (CheckConstraint("amount_cents >= 1", name="amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(32))
    amount_cents: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str] = mapped_column(String(64), default="")
    # Foreign cash: what the customer handed over, the rate used, and the business-currency change given back.
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    foreign_amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rate_micros: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    change_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sale: Mapped[Sale] = relationship("Sale", back_populates="tenders")
