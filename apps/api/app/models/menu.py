"""Menu modifiers: option groups (size, milk, extras) linked to products, priced per option.
Meal combos: slots (Main, Side, Drink) on a combo product, each offering real menu items."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class ModifierGroup(TenantScoped, TimestampMixin, Base):
    __tablename__ = "modifier_groups"
    __table_args__ = (
        CheckConstraint("min_select >= 0", name="min_nonnegative"),
        CheckConstraint("max_select >= 1", name="max_positive"),
        CheckConstraint("max_select >= min_select", name="max_covers_min"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    # How many options the cashier must / may pick; min_select >= 1 makes the group required.
    min_select: Mapped[int] = mapped_column(Integer, default=0)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Loaded by the signup starter kit; Go live removes it with the sample menu.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    options: Mapped[list[ModifierOption]] = relationship(
        "ModifierOption",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="ModifierOption.position",
        lazy="selectin",
    )


class ModifierOption(TenantScoped, TimestampMixin, Base):
    __tablename__ = "modifier_options"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("modifier_groups.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    # Added to the item's unit price; negative for "no cheese"-style reductions.
    price_delta_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    group: Mapped[ModifierGroup] = relationship("ModifierGroup", back_populates="options")


class ProductModifierGroup(TenantScoped, Base):
    __tablename__ = "product_modifier_groups"

    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("modifier_groups.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)


class ComboSlot(TenantScoped, TimestampMixin, Base):
    """One choice in a meal, e.g. "Side": the cashier picks between min_select and max_select of its options."""

    __tablename__ = "combo_slots"
    __table_args__ = (
        CheckConstraint("min_select >= 0", name="min_nonnegative"),
        CheckConstraint("max_select >= 1", name="max_positive"),
        CheckConstraint("max_select >= min_select", name="max_covers_min"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The combo (meal) product; it is a service item, its components carry the stock.
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    min_select: Mapped[int] = mapped_column(Integer, default=1)
    max_select: Mapped[int] = mapped_column(Integer, default=1)
    position: Mapped[int] = mapped_column(Integer, default=0)
    options: Mapped[list[ComboSlotOption]] = relationship(
        "ComboSlotOption",
        back_populates="slot",
        cascade="all, delete-orphan",
        order_by="ComboSlotOption.position",
        lazy="selectin",
    )


class ComboSlotOption(TenantScoped, Base):
    __tablename__ = "combo_slot_options"
    __table_args__ = (
        CheckConstraint("surcharge_cents >= 0", name="surcharge_nonnegative"),
        tenant_unique("slot_id", "product_id", name="uq_combo_slot_options_slot_product"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slot_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("combo_slots.id", ondelete="CASCADE"), index=True
    )
    # A real menu item; it routes to its own kitchen station and draws its own stock or recipe.
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    # Added to the meal price when picked, e.g. +3.00 for onion rings instead of fries.
    surcharge_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int] = mapped_column(Integer, default=0)
    slot: Mapped[ComboSlot] = relationship("ComboSlot", back_populates="options")
