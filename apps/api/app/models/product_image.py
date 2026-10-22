import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ProductImage(TimestampMixin, Base):
    """A product photo, attached to one variant or to a whole model. A model photo may be tied to one value of an
    attribute (colour = Black) so the register shows the colour the cashier picked."""

    __tablename__ = "product_images"
    __table_args__ = (
        CheckConstraint(
            "(product_id IS NOT NULL) <> (product_model_id IS NOT NULL)", name="product_image_owner_exactly_one"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True
    )
    product_model_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("product_models.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Variant attribute this model photo shows, e.g. ("color", "Black"); null for the model's general photos.
    attribute_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attribute_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Storage keys under the tenant's media folder: the 1200 px image and the 320 px thumbnail (both WebP).
    key: Mapped[str] = mapped_column(String(160), unique=True)
    thumb_key: Mapped[str] = mapped_column(String(160), unique=True)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
