import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TENANT_STATUSES = ("active", "suspended")
DATA_PLANES = ("legacy", "shared")
SIGNUP_STATUSES = ("PENDING_OTP", "VERIFIED", "WAITLIST", "PROVISIONING", "READY", "FAILED")


def _now() -> datetime:
    return datetime.now(UTC)


class ControlBase(DeclarativeBase):
    """Tables of the control database only; tenant databases use app.models.Base."""

    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class Tenant(ControlBase):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="active")
    # Business type chosen at provisioning; the tenant's own business_settings row is the source of truth.
    profile: Mapped[str] = mapped_column(String(32), default="electronics_wholesale")
    # Full SQLAlchemy URL of a legacy tenant database, Fernet-encrypted with ENCRYPTION_SECRET.
    # Shared tenants still store a URL, but requests use DATABASE_URL instead.
    database_url_encrypted: Mapped[str] = mapped_column(Text)
    # "legacy" keeps a private database. "shared" uses the one operational database.
    data_plane: Mapped[str] = mapped_column(String(16), default="legacy")
    # Subscription tier shown in the console directory. Matches a billing_plans.code when one is assigned.
    plan: Mapped[str] = mapped_column(String(32), default="standard")
    # Copy of the store's live_at being unset, so the directory does not open every store database.
    practice_mode: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


OPERATOR_ROLES = ("SUPPORT", "ADMIN")
OVERRIDE_STATES = ("on", "off")


class TenantModuleOverride(ControlBase):
    """A module IT support forced on or off for one tenant; the tenant's own database holds the applied copy."""

    __tablename__ = "tenant_module_overrides"
    __table_args__ = (UniqueConstraint("tenant_id", "module_key", name="uq_tenant_module_overrides_tenant_module"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    module_key: Mapped[str] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(8))
    reason: Mapped[str] = mapped_column(Text)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("operators.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Operator(ControlBase):
    """POS-company staff who run the console. They are not users of any store and sign in with their own tokens."""

    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    # Base32 TOTP key, Fernet-encrypted with ENCRYPTION_SECRET.
    totp_secret_enc: Mapped[str] = mapped_column(Text)
    # SUPPORT works tenants; ADMIN can also reveal customer contacts and manage operators.
    role: Mapped[str] = mapped_column(String(16), default="SUPPORT")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Bumped to sign the operator out everywhere.
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class OperatorAuditLog(ControlBase):
    """Every console action, with the operator, the tenant it touched, and why."""

    __tablename__ = "operator_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("operators.id"), nullable=True, index=True
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class TenantStats(ControlBase):
    """Each store's size and activity, collected from its own database so the console directory never opens
    every tenant database on page load."""

    __tablename__ = "tenant_stats"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    business_profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    enabled_modules: Mapped[list] = mapped_column(JSON, default=list)
    stores: Mapped[int] = mapped_column(Integer, default=0)
    registers: Mapped[int] = mapped_column(Integer, default=0)
    users: Mapped[int] = mapped_column(Integer, default=0)
    customers: Mapped[int] = mapped_column(Integer, default=0)
    products: Mapped[int] = mapped_column(Integer, default=0)
    sales_30d_count: Mapped[int] = mapped_column(Integer, default=0)
    sales_30d_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    last_sale_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    db_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TenantChangeRequest(ControlBase):
    """A tenant asking IT support for what the portal does not do by itself: a new business type (a data migration)
    or a module outside its type. `snapshot` holds the store's size when it asked, for the migration checks."""

    __tablename__ = "tenant_change_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    requested_value: Mapped[str] = mapped_column(String(40))
    current_value: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    requested_by_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    requested_by_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resolved_by_operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SignupRequest(ControlBase):
    """A self-service signup on the bare domain, from the first form to a provisioned store.

    The password is hashed here and copied (still hashed) to the store's owner account; the one-time code is
    hashed too. `steps` is the provisioning checklist the signup screen polls."""

    __tablename__ = "signup_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # One signup per email and per mobile. The availability check is advisory; these constraints close the race.
    email: Mapped[str] = mapped_column(String(254), unique=True)
    phone: Mapped[str] = mapped_column(String(32), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(Text)
    # SHA-256 of the token returned at start; every later step must present it.
    access_hash: Mapped[str] = mapped_column(String(64))
    otp_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sub_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    store_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    slug: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    trn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING_OTP", index=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    owner_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handoff_jti: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    handoff_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SignupSlugHold(ControlBase):
    """The store address a signup is provisioning.

    Released when setup fails before a tenant exists, so another store can use that address.
    A live tenant keeps the address on tenants.slug. Display names are not unique and have no hold.
    """

    __tablename__ = "signup_slug_holds"

    slug: Mapped[str] = mapped_column(String(32), primary_key=True)
    signup_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("signup_requests.id"), index=True)


SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "canceled")


class BillingPlan(ControlBase):
    """A package the POS company sells. Prices are fils per month before the billing-cycle discount."""

    __tablename__ = "billing_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    included_registers: Mapped[int] = mapped_column(Integer, default=1)
    included_modules: Mapped[list] = mapped_column(JSON, default=list)
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    trial_days: Mapped[int] = mapped_column(Integer, default=14)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingCycle(ControlBase):
    """How far ahead the store pays. discount_bps is editable; 500 is 5 percent."""

    __tablename__ = "billing_cycles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    months: Mapped[int] = mapped_column(Integer)
    discount_bps: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingAddon(ControlBase):
    """Hardware lease, protection, or an extra register. The one-time amount can be a refundable deposit."""

    __tablename__ = "billing_addons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    one_time_fils: Mapped[int] = mapped_column(Integer, default=0)
    refundable: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Capability keys this commercial add-on is allowed to unlock. Empty means it bills only and grants nothing.
    module_keys: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingFee(ControlBase):
    """One-time charges such as onboarding. Not discounted by the billing cycle."""

    __tablename__ = "billing_fees"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    amount_fils: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Subscription(ControlBase):
    """The store's current package. Invoice lines snapshot the fils that were actually charged."""

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), unique=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("billing_plans.id"))
    cycle_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("billing_cycles.id"))
    status: Mapped[str] = mapped_column(String(16), default="trialing")
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SubscriptionItem(ControlBase):
    __tablename__ = "subscription_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("subscriptions.id"), index=True)
    addon_code: Mapped[str] = mapped_column(String(32))
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class BillingInvoice(ControlBase):
    """A go-live checkout. Pending until Stripe or the simulator pays it, then the stored purge runs."""

    __tablename__ = "billing_invoices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    plan_code: Mapped[str] = mapped_column(String(32))
    cycle_code: Mapped[str] = mapped_column(String(32))
    recurring_fils: Mapped[int] = mapped_column(Integer, default=0)
    one_time_fils: Mapped[int] = mapped_column(Integer, default=0)
    total_fils: Mapped[int] = mapped_column(Integer, default=0)
    purge: Mapped[str] = mapped_column(String(16), default="keep")
    opening_stock: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirm_name: Mapped[str] = mapped_column(String(120))
    stripe_session_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Bank instructions copied when the invoice was issued. Later account edits do not rewrite this.
    bank_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# Prefilled chat text for a new marketing-site row. Migrations freeze their own copy of this sentence.
WHATSAPP_MESSAGE_DEFAULT = (
    "Hello AxizPOS Sales Team! I would like to learn more about your POS solutions for my business."
)
WHATSAPP_TOOLTIP_DEFAULT = "Chat with Sales"


class SiteSettings(ControlBase):
    """One row for the public marketing site. The WhatsApp number is digits with the country code, or blank."""

    __tablename__ = "site_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Digits with the country code, no leading plus. Blank hides the button.
    whatsapp: Mapped[str] = mapped_column(String(16), default="")
    message: Mapped[str] = mapped_column(String(500), default=WHATSAPP_MESSAGE_DEFAULT)
    tooltip: Mapped[str] = mapped_column(String(40), default=WHATSAPP_TOOLTIP_DEFAULT)
    # Public sales address for the site footer. Blank hides the link. Not the outgoing mailbox.
    email: Mapped[str] = mapped_column(String(254), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MailSettings(ControlBase):
    """The mailbox the platform uses to email store users (password reset and other notices)."""

    __tablename__ = "mail_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    host: Mapped[str] = mapped_column(String(255), default="")
    port: Mapped[int] = mapped_column(Integer, default=465)
    # ssl (implicit TLS, port 465), starttls (port 587), or none.
    security: Mapped[str] = mapped_column(String(16), default="ssl")
    username: Mapped[str] = mapped_column(String(254), default="")
    password_encrypted: Mapped[str] = mapped_column(Text, default="")
    from_address: Mapped[str] = mapped_column(String(254), default="")
    from_name: Mapped[str] = mapped_column(String(120), default="AI POS")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TenantMergeCheckpoint(ControlBase):
    """One finished table in a legacy-to-shared copy. A rerun skips tables already recorded."""

    __tablename__ = "tenant_merge_checkpoints"
    __table_args__ = (UniqueConstraint("tenant_id", "table_name", name="uq_tenant_merge_checkpoints_table"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    table_name: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlatformBankAccount(ControlBase):
    """Payment instructions printed on invoices. A later edit does not change invoices already issued."""

    __tablename__ = "platform_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str] = mapped_column(String(80))
    bank_name: Mapped[str] = mapped_column(String(120))
    holder_name: Mapped[str] = mapped_column(String(120))
    account_number: Mapped[str] = mapped_column(String(40), default="")
    iban: Mapped[str] = mapped_column(String(40), default="")
    swift: Mapped[str] = mapped_column(String(16), default="")
    country: Mapped[str] = mapped_column(String(2), default="AE")
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    instructions: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingPolicy(ControlBase):
    """One row. Grace is applied at request time from the paid-through date, not only by a scheduler."""

    __tablename__ = "billing_policy"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grace_days: Mapped[int] = mapped_column(Integer, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class BillingTransfer(ControlBase):
    """A tenant's claim that they paid. The receipt is evidence. It is not a verified payment."""

    __tablename__ = "billing_transfers"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_billing_transfers_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("billing_invoices.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_review", index=True)
    amount_fils: Mapped[int] = mapped_column(Integer)
    transferred_on: Mapped[str] = mapped_column(String(10))
    bank_reference: Mapped[str] = mapped_column(String(80), default="")
    sending_bank: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    filename: Mapped[str] = mapped_column(String(120))
    content_type: Mapped[str] = mapped_column(String(40))
    body: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class BillingPayment(ControlBase):
    """A bank credit an administrator verified. One submission can produce at most one payment."""

    __tablename__ = "billing_payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("billing_invoices.id"), index=True)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_transfers.id"), unique=True
    )
    amount_fils: Mapped[int] = mapped_column(Integer)
    bank_reference: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Set when an administrator undoes an activation. The payment row itself stays.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsolePaymentNotice(ControlBase):
    """One console alert per payment proof. Reading it does not review the transfer."""

    __tablename__ = "console_payment_notices"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transfer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_transfers.id"), unique=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    tenant_name: Mapped[str] = mapped_column(String(120), default="")
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    invoice_reference: Mapped[str] = mapped_column(String(48), default="")
    amount_fils: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class ConsolePaymentNoticeRead(ControlBase):
    """Per-operator read mark. It is not a payment decision."""

    __tablename__ = "console_payment_notice_reads"
    __table_args__ = (UniqueConstraint("notice_id", "operator_id", name="uq_console_payment_notice_reads"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    notice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("console_payment_notices.id"), index=True
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("operators.id"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class HardwareCategory(ControlBase):
    """A catalogue group such as receipt printers. Administrators can add more without a code change."""

    __tablename__ = "hardware_categories"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class HardwareItem(ControlBase):
    """One product a tenant may lease or buy. Prices are fils. A later edit does not rewrite an issued invoice."""

    __tablename__ = "hardware_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sku: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("hardware_categories.id"), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    manufacturer: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    lease_available: Mapped[bool] = mapped_column(Boolean, default=True)
    purchase_available: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    deposit_fils: Mapped[int] = mapped_column(Integer, default=0)
    fee_fils: Mapped[int] = mapped_column(Integer, default=0)
    purchase_fils: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_fils: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    min_qty: Mapped[int] = mapped_column(Integer, default=1)
    max_qty: Mapped[int] = mapped_column(Integer, default=20)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counts_as_register: Mapped[bool] = mapped_column(Boolean, default=False)
    compatibility: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class HardwareOrder(ControlBase):
    """A tenant's hardware selection. Payment status and fulfillment status are independent."""

    __tablename__ = "hardware_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(String(20), unique=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("billing_invoices.id"), index=True
    )
    payment_status: Mapped[str] = mapped_column(String(24), default="awaiting_payment", index=True)
    fulfillment_status: Mapped[str] = mapped_column(String(24), default="awaiting_payment", index=True)
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    deposit_fils: Mapped[int] = mapped_column(Integer, default=0)
    one_time_fils: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="AED")
    notes: Mapped[str] = mapped_column(Text, default="")
    assigned_operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class HardwareOrderLine(ControlBase):
    __tablename__ = "hardware_order_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("hardware_orders.id"), index=True)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("hardware_items.id"), index=True)
    sku: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(120))
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    store_label: Mapped[str] = mapped_column(String(80), default="")
    mode: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int] = mapped_column(Integer)
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    deposit_fils: Mapped[int] = mapped_column(Integer, default=0)
    fee_fils: Mapped[int] = mapped_column(Integer, default=0)
    purchase_fils: Mapped[int] = mapped_column(Integer, default=0)
    delivery_fils: Mapped[int] = mapped_column(Integer, default=0)
    fulfilled_qty: Mapped[int] = mapped_column(Integer, default=0)
    serials: Mapped[list] = mapped_column(JSON, default=list)


class HardwareAssignment(ControlBase):
    """A leased unit after payment. Paying the invoice does not mark it delivered or refund the deposit."""

    __tablename__ = "hardware_assignments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("tenants.id"), index=True)
    order_line_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("hardware_order_lines.id"), index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("hardware_items.id"))
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    store_label: Mapped[str] = mapped_column(String(80), default="")
    serial: Mapped[str] = mapped_column(String(64), default="")
    quantity: Mapped[int] = mapped_column(Integer)
    monthly_fils: Mapped[int] = mapped_column(Integer, default=0)
    deposit_fils: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    condition_note: Mapped[str] = mapped_column(Text, default="")
    deposit_decision: Mapped[str] = mapped_column(String(24), default="held")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BillingInvoiceLine(ControlBase):
    __tablename__ = "billing_invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("billing_invoices.id"), index=True)
    code: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_fils: Mapped[int] = mapped_column(Integer, default=0)
    amount_fils: Mapped[int] = mapped_column(Integer, default=0)
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    refundable: Mapped[bool] = mapped_column(Boolean, default=False)


class RecoveryChallenge(ControlBase):
    """One emailed recovery code for an address. The code is stored only as a hash."""

    __tablename__ = "recovery_challenges"
    __table_args__ = (UniqueConstraint("purpose", "email", name="uq_recovery_challenges_purpose_email"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(32))
    email: Mapped[str] = mapped_column(String(254), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
