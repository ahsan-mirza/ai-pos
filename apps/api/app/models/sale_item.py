from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, tenant_unique
from app.models.product import Product
from app.models.serial_number import SerialNumber

if TYPE_CHECKING:
    from app.models.sale import Sale


class SaleItem(TenantScoped, Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        tenant_unique("gift_card_code", name="uq_sale_items_gift_card_code"),
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="unit_price_nonnegative"),
        CheckConstraint("tax_cents >= 0", name="tax_nonnegative"),
        CheckConstraint("line_total_cents >= 0", name="line_total_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("serial_numbers.id"),
        nullable=True,
    )
    # quantity and unit_price_cents are always per piece; unit_type/unit_factor record the pack it was sold in.
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer)
    line_total_cents: Mapped[int] = mapped_column(Integer)
    unit_type: Mapped[str] = mapped_column(String(16), default="PIECE")
    unit_factor: Mapped[int] = mapped_column(Integer, default=1)
    list_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tax_rate_bps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # What was sold, copied at the till so a later rename or price change does not rewrite history.
    product_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variant_attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # FIFO cost of the units drawn (falls back to the latest purchase cost for unbatched stock).
    cost_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimated: Mapped[bool] = mapped_column(Boolean, default=False)
    # Margin floor in force when sold; set only when the unit price was below it (an exception).
    floor_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    below_floor_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    price_override_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # Promotion discount taken off unit_price_cents * quantity before VAT; line_total_cents is after it.
    discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    promotion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("promotions.id"), nullable=True, index=True
    )
    # Cashier discount taken after the promotion, before VAT; a reason code from pos_policy, approved above the
    # cashier's own limit.
    manual_discount_cents: Mapped[int] = mapped_column(Integer, default=0)
    discount_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    discount_approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # The gift card this line sold (a GIFT_CARD store credit with this code).
    gift_card_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Sold as final sale (marked down or flagged); returns need a manager.
    final_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    # Menu modifiers chosen for this line, as sold: [{"group_id", "group", "option_id", "option", "price_delta_cents"}].
    # unit_price_cents already includes the price deltas.
    modifiers: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Meal components chosen for a combo line, as sold: [{"slot_id", "slot", "product_id", "name", "surcharge_cents"}].
    # unit_price_cents already includes the surcharges; each component drew its own stock or recipe.
    components: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The sales order line this sale line delivers.
    sales_order_line_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    # Where the listed price came from (retail, tier, volume, customer_list, group_list, store_list, global_list)
    # when it matched the server's resolution, and the price list behind it.
    price_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    price_list_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # The customer's VAT treatment when it zero-rated or exempted this line (ZERO_EXPORT, EXEMPT, DESIGNATED_ZONE).
    tax_treatment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # The first purchase batch this line drew from; batch_allocations holds the full FIFO split.
    batch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batch_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sale: Mapped[Sale] = relationship("Sale", back_populates="items")
    product: Mapped[Product] = relationship()
    serial_number: Mapped[SerialNumber | None] = relationship()
