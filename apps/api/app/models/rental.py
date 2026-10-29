"""Fashion rentals. A product stays in the catalogue; these rows only record how it can be rented."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

OFFERS = ("SALE", "RENT", "BOTH")
RENTAL_STATUSES = ("confirmed", "ready", "out", "inspection", "cleaning", "repair", "completed", "cancelled")
BLOCKING_STATUSES = ("confirmed", "ready", "out", "inspection", "cleaning", "repair")
HELD_STATUSES = ("out", "inspection", "cleaning", "repair")
PAYMENT_KINDS = ("charge", "deposit", "deposit_refund", "deduction")


class ProductRental(TenantScoped, TimestampMixin, Base):
    """Rental terms for one catalogue product. Sale prices stay on the product."""

    __tablename__ = "product_rentals"
    __table_args__ = (
        tenant_unique("product_id", name="uq_product_rentals_product"),
        CheckConstraint("offer IN ('SALE', 'RENT', 'BOTH')", name="offer_known"),
        CheckConstraint("price_per_day_cents >= 0", name="daily_nonnegative"),
        CheckConstraint("weekly_price_cents IS NULL OR weekly_price_cents >= 0", name="weekly_nonnegative"),
        CheckConstraint("deposit_cents >= 0", name="deposit_nonnegative"),
        CheckConstraint("min_days >= 1", name="min_days_positive"),
        CheckConstraint("max_days IS NULL OR max_days >= min_days", name="max_covers_min"),
        CheckConstraint("default_days >= min_days", name="default_in_range"),
        CheckConstraint("buffer_days >= 0 AND buffer_days <= 30", name="buffer_range"),
        CheckConstraint("late_fee_per_day_cents >= 0", name="late_nonnegative"),
        CheckConstraint("cleaning_fee_cents >= 0", name="cleaning_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    offer: Mapped[str] = mapped_column(String(8), default="BOTH")
    price_per_day_cents: Mapped[int] = mapped_column(Integer, default=0)
    weekly_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deposit_cents: Mapped[int] = mapped_column(Integer, default=0)
    min_days: Mapped[int] = mapped_column(Integer, default=1)
    max_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_days: Mapped[int] = mapped_column(Integer, default=1)
    buffer_days: Mapped[int] = mapped_column(Integer, default=0)
    late_fee_per_day_cents: Mapped[int] = mapped_column(Integer, default=0)
    cleaning_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    requires_inspection: Mapped[bool] = mapped_column(Boolean, default=True)
    condition_note: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Rental(TenantScoped, TimestampMixin, Base):
    __tablename__ = "rentals"
    __table_args__ = (
        tenant_unique("reference", name="uq_rentals_reference"),
        tenant_unique("client_request_id", name="uq_rentals_client_request"),
        CheckConstraint(
            "status IN ('confirmed', 'ready', 'out', 'inspection', 'cleaning', 'repair', 'completed', 'cancelled')",
            name="status_known",
        ),
        CheckConstraint("agreed_net_cents >= 0", name="agreed_nonnegative"),
        CheckConstraint("discount_cents >= 0", name="discount_nonnegative"),
        CheckConstraint("extension_net_cents >= 0", name="extension_nonnegative"),
        CheckConstraint("tax_cents >= 0 AND extension_tax_cents >= 0", name="tax_nonnegative"),
        CheckConstraint("late_fee_cents >= 0", name="late_nonnegative"),
        CheckConstraint("cleaning_fee_cents >= 0 AND damage_cents >= 0", name="fees_nonnegative"),
        CheckConstraint("amount_paid_cents >= 0", name="paid_nonnegative"),
        CheckConstraint("deposit_due_cents >= 0 AND deposit_collected_cents >= 0", name="deposit_due_nonnegative"),
        CheckConstraint("deposit_refunded_cents >= 0 AND deposit_deducted_cents >= 0", name="deposit_out_nonnegative"),
        Index("ix_rentals_store_status", "store_id", "status"),
        Index("ix_rentals_dates", "start_date", "return_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(20))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="confirmed")
    start_date: Mapped[date] = mapped_column(Date)
    return_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    agreed_net_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    extension_net_cents: Mapped[int] = mapped_column(Integer, default=0)
    extension_tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    late_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    cleaning_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    damage_cents: Mapped[int] = mapped_column(Integer, default=0)
    amount_paid_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_due_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_collected_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_refunded_cents: Mapped[int] = mapped_column(Integer, default=0)
    deposit_deducted_cents: Mapped[int] = mapped_column(Integer, default=0)
    deduction_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    waived_late_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    handover_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handover_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    handover_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    return_condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    return_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class RentalLine(TenantScoped, Base):
    __tablename__ = "rental_lines"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        Index("ix_rental_lines_product", "product_id", "rental_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rental_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rentals.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("serial_numbers.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RentalPayment(TenantScoped, Base):
    """One movement of rental charges or the refundable deposit. Replaying the request id does nothing."""

    __tablename__ = "rental_payments"
    __table_args__ = (
        tenant_unique("client_request_id", name="uq_rental_payments_request"),
        CheckConstraint("kind IN ('charge', 'deposit', 'deposit_refund', 'deduction')", name="kind_known"),
        CheckConstraint("amount_cents > 0", name="amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rental_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("rentals.id"), index=True)
    client_request_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20))
    amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
