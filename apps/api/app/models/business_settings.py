from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin
from app.models.user import User


class BusinessSettings(TenantScoped, TimestampMixin, Base):
    """Single row (BUSINESS_SETTINGS_ID) holding settings that apply to every store and register."""

    __tablename__ = "business_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    currency: Mapped[str] = mapped_column(String(3))
    # VAT. While vat_registered is false the API keeps the register's line tax as sent (legacy behaviour).
    vat_registered: Mapped[bool] = mapped_column(Boolean, default=False)
    trn: Mapped[str | None] = mapped_column(String(15), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    legal_name_ar: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Switching this reinterprets every catalog price, so it is an explicit business decision.
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, default=False)
    standard_rate_bps: Mapped[int] = mapped_column(Integer, default=500)
    # Which tax authority's invoicing rules apply (app.tax_authority): "fta" (UAE) or "zatca" (Saudi Arabia).
    tax_authority: Mapped[str] = mapped_column(String(8), default="fta")
    # Provider per channel, e.g. {"whatsapp": "log", "sms": "http_sms", "email": "smtp"}; credentials stay in env.
    messaging: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Which events message customers automatically, e.g. {"receipt": true, "overdue_reminder": true}.
    message_events: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # {"enabled": bool, "earn_per_unit": points per whole currency unit paid, "redeem_cents": value of one point,
    #  "min_redeem": smallest redemption}
    loyalty: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Overrides of the journal export's chart of accounts: {"cash": {"code": "1001", "name": "Till float"}, ...}.
    gl_accounts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # WPS employer details: {"employer_id": 13-digit MOHRE establishment ID, "bank_routing_code": 9 digits}.
    payroll: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # General ledger: {"locked_until": "YYYY-MM-DD", "fiscal_year_start_month": 1-12}.
    accounting: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Admin portal accent as "#RRGGBB"; None keeps the brand default.
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # Business type preset (app.core.capabilities.PROFILES) and the merchant's own module selection;
    # capabilities=None means "use the profile preset".
    business_profile: Mapped[str] = mapped_column(String(32), default="electronics_wholesale")
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Modules IT support forced on or off from the console, {"serial_tracking": "on"}; the tenant cannot change them.
    managed_capabilities: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Per-module configuration validated by app.schemas.module_settings.ModuleSettings; None keeps the defaults.
    module_settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Receipt branding validated by app.schemas.receipt.ReceiptSettings (logo, header/footer notes, contact lines).
    # Names, TRN, address and phone are not copied here: receipts read them from these settings and the store.
    receipt: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Till rules validated by app.schemas.pos_policy: discount reasons and limits, gift cards, the returns policy.
    pos_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Set when a business-wide admin finishes the onboarding wizard; None shows the wizard.
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # When the business went live. Self-service signup clears it (practice mode with sample data) until the owner
    # runs Go live; stores created any other way are live from the start.
    live_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=lambda: datetime.now(UTC)
    )
    # Set by Go live. Sync then refuses events that happened before live_at, so a till cannot replay practice
    # sales. Stores that were live from the start leave this false and keep accepting earlier offline events.
    promoted_from_practice: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
    updated_by: Mapped[User | None] = relationship(lazy="joined")
