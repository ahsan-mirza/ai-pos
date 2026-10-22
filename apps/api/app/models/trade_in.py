from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

TRADE_IN_GRADES = ("A", "B", "C", "D")
TRADE_IN_PAYOUTS = ("CASH", "STORE_CREDIT", "SALE_CREDIT")


class TradeIn(TimestampMixin, Base):
    """A used device bought from a customer. The unit enters stock under a pre-owned SKU for its model and grade,
    costed at the price paid. SALE_CREDIT trade-ins wait (ACCEPTED) until a sale spends them (APPLIED)."""

    __tablename__ = "trade_ins"
    __table_args__ = (CheckConstraint("offer_cents >= 0", name="trade_in_offer_nonnegative"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # The catalog model the customer brought in, and the pre-owned SKU the unit is stocked under.
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    resale_product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    serial_number_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("serial_numbers.id"))
    identifier_kind: Mapped[str] = mapped_column(String(16))
    identifier_hash: Mapped[str] = mapped_column(String(64), index=True)
    grade: Mapped[str] = mapped_column(String(1))
    # {"powers_on": bool, "screen_ok": bool, "body_ok": bool, "account_removed": bool, "battery_pct": int}
    checklist: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(String(500), default="")
    seller_name: Mapped[str] = mapped_column(String(120))
    seller_phone: Mapped[str] = mapped_column(String(40))
    # Emirates ID or passport number, encrypted; the last four characters are kept for display.
    seller_id_encrypted: Mapped[str] = mapped_column(Text)
    seller_id_last4: Mapped[str] = mapped_column(String(4))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    offer_cents: Mapped[int] = mapped_column(Integer)
    resale_price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    payout: Mapped[str] = mapped_column(String(12))
    # ACCEPTED, APPLIED (sale credit spent), CANCELLED
    status: Mapped[str] = mapped_column(String(10), default="ACCEPTED", index=True)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    store_credit_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("store_credits.id"), nullable=True
    )
    batch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batch_items.id"), nullable=True
    )
    cashier_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
