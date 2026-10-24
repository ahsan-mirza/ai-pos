"""Recipes: what a dish is made of. Selling a dish draws its ingredients from stock instead of the dish itself."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class Recipe(TenantScoped, TimestampMixin, Base):
    __tablename__ = "recipes"
    __table_args__ = (
        tenant_unique("product_id", name="uq_recipes_product_id"),
        CheckConstraint("yield_quantity >= 1", name="yield_positive"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE")
    )
    # How much one batch of the lines makes, in the dish's units (portions, or grams for a dish sold by weight).
    yield_quantity: Mapped[int] = mapped_column(Integer, default=1)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lines: Mapped[list[RecipeLine]] = relationship(
        "RecipeLine", cascade="all, delete-orphan", order_by="RecipeLine.position", lazy="selectin"
    )


class RecipeLine(TenantScoped, Base):
    __tablename__ = "recipe_lines"
    __table_args__ = (
        tenant_unique("recipe_id", "ingredient_id", name="uq_recipe_lines_recipe_ingredient"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("recipes.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    # In the ingredient's stock units: grams for an ingredient kept by weight, else pieces (or ml).
    quantity: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)


class ModifierIngredient(TenantScoped, Base):
    """A modifier option changes what goes in the dish: "extra shot" adds 18 g of coffee, "no cheese" takes 20 g off."""

    __tablename__ = "modifier_ingredients"
    __table_args__ = (
        tenant_unique("option_id", "ingredient_id", name="uq_modifier_ingredients_option_ingredient"),
        CheckConstraint("quantity <> 0", name="quantity_nonzero"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    option_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("modifier_options.id", ondelete="CASCADE"), index=True
    )
    ingredient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    # Per dish unit sold; negative takes the ingredient out.
    quantity: Mapped[int] = mapped_column(Integer)


class RecipeUsage(TenantScoped, Base):
    """What each sale should have used (theoretical usage) and what stock actually covered; the gap is a shortfall
    the kitchen used without the system holding the stock."""

    __tablename__ = "recipe_usages"
    __table_args__ = (Index("ix_recipe_usages_store_ingredient_created", "store_id", "ingredient_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    ingredient_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"))
    quantity_needed: Mapped[int] = mapped_column(Integer)
    quantity_drawn: Mapped[int] = mapped_column(Integer)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
