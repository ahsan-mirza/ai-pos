from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

CUSTOMER_TYPES = ("RETAIL", "WHOLESALE")
PRICE_TIERS = ("RETAIL", "TIER_1", "TIER_2", "DISTRIBUTOR")
PAYMENT_TERMS = ("DUE_ON_RECEIPT", "NET_15", "NET_30", "NET_60")
TERM_DAYS = {"DUE_ON_RECEIPT": 0, "NET_15": 15, "NET_30": 30, "NET_60": 60}
LEDGER_ENTRY_TYPES = ("INVOICE", "PAYMENT", "ADJUSTMENT")


class Customer(TenantScoped, TimestampMixin, Base):
    """B2B or walk-in account. Only services.ledger_service writes current_balance_cents."""

    __tablename__ = "customers"
    __table_args__ = (
        tenant_unique("code", name="uq_customers_code"),
        CheckConstraint("credit_limit_cents >= 0", name="credit_limit_nonnegative"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    customer_type: Mapped[str] = mapped_column(String(16), index=True, default="RETAIL")
    company_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    trn_vat_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_tier: Mapped[str] = mapped_column(String(16), default="RETAIL")
    credit_limit_cents: Mapped[int] = mapped_column(Integer, default=0)
    current_balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    payment_terms: Mapped[str] = mapped_column(String(16), default="DUE_ON_RECEIPT")
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Practice customer loaded at signup; Go live deletes it.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set automatically (bounced cheque, invoices overdue past the grace period) or by a manager; blocks
    # new on-account sales until cleared.
    credit_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    credit_hold_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    credit_hold_manual: Mapped[bool] = mapped_column(Boolean, default=False)
    # Consent per channel (UAE PDPL): nothing is sent on a channel the customer has not opted into.
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    email_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    # Only services.loyalty_service writes this; loyalty_entries is the ledger behind it.
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    # Latest credit risk (services.credit_risk_service): 0-100 score, grade A-E, and its factors and suggestions.
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_grade: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    risk_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_groups.id"), nullable=True, index=True
    )
    # STANDARD, ZERO_EXPORT, EXEMPT or DESIGNATED_ZONE: standard-rated lines are taxed at 0 for the last three
    # while the certificate is valid (no expiry, or not yet expired).
    tax_treatment: Mapped[str] = mapped_column(String(16), default="STANDARD")
    tax_certificate_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tax_certificate_expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(12), nullable=True)
    preferred_sizes: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)

    @property
    def available_credit_cents(self) -> int:
        return self.credit_limit_cents - self.current_balance_cents


class CustomerLedgerEntry(TenantScoped, Base):
    """Append-only statement of account. amount_cents is signed: invoices raise the balance, payments lower it."""

    __tablename__ = "customer_ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_cents <> 0", name="amount_nonzero"),
        Index("ix_customer_ledger_entries_customer_created", "customer_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(16), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    balance_after_cents: Mapped[int] = mapped_column(Integer)
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reference: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(String(255), default="")
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


COUPON_STATUSES = ("issued", "redeemed", "revoked", "expired")


class CustomerCoupon(TenantScoped, Base):
    """A code issued to one customer for an existing promotion. It is not a second discount engine."""

    __tablename__ = "customer_coupons"
    __table_args__ = (
        tenant_unique("code", name="uq_customer_coupons_code"),
        tenant_unique("idempotency_key", name="uq_customer_coupons_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    promotion_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("promotions.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="issued", index=True)
    reason: Mapped[str] = mapped_column(String(255), default="")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True
    )
