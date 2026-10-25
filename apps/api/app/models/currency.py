from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, utcnow


class AcceptedCurrency(TenantScoped, TimestampMixin, Base):
    """A foreign currency registers may take as cash, priced into the business currency at the latest rate."""

    __tablename__ = "accepted_currencies"
    __table_args__ = (PrimaryKeyConstraint("tenant_id", "code", name="pk_accepted_currencies"),)

    code: Mapped[str] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(60))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ExchangeRate(TenantScoped, Base):
    """Business-currency units per one foreign unit, times 1,000,000. Append-only: the latest row is in force."""

    __tablename__ = "exchange_rates"
    __table_args__ = (
        CheckConstraint("rate_micros > 0", name="rate_positive"),
        ForeignKeyConstraint(
            ["tenant_id", "currency"],
            ["accepted_currencies.tenant_id", "accepted_currencies.code"],
            name="fk_exchange_rates_tenant_currency_accepted_currencies",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    base_currency: Mapped[str] = mapped_column(String(3))
    rate_micros: Mapped[int] = mapped_column(BigInteger)
    source: Mapped[str] = mapped_column(String(24))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
