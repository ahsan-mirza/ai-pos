"""A branch's own tax profile, separate from the business-wide settings it can still inherit.

The legal entity is not the branch. Several branches in one country can share an entity.
A branch in another country gets its own entity rather than reusing the first country's registration.
Posted sales keep a tax snapshot, so later edits here do not rewrite invoices.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class LegalEntity(TenantScoped, TimestampMixin, Base):
    __tablename__ = "legal_entities"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(2))
    legal_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    legal_name_local: Mapped[str | None] = mapped_column(String(160), nullable=True)


class BranchTaxProfile(TenantScoped, TimestampMixin, Base):
    __tablename__ = "branch_tax_profiles"
    __table_args__ = (tenant_unique("store_id", name="uq_branch_tax_store"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    legal_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("legal_entities.id"), nullable=True
    )
    # Empty until this branch is given its own country. own=False keeps the business-wide tax settings.
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    region: Mapped[str | None] = mapped_column(String(80), nullable=True)
    own: Mapped[bool] = mapped_column(Boolean, default=False)
    registered: Mapped[bool] = mapped_column(Boolean, default=False)
    registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    secondary_registration_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legal_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    legal_name_local: Mapped[str | None] = mapped_column(String(160), nullable=True)
    prices_include_vat: Mapped[bool] = mapped_column(Boolean, default=False)
    standard_rate_bps: Mapped[int] = mapped_column(Integer, default=0)
    tax_authority: Mapped[str] = mapped_column(String(8), default="fta")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # False while a registered branch still needs a rate confirmed for its country.
    rate_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
