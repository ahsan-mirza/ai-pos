from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.auth import ApiModel

CatalogueView = Literal["grid", "list", "compact"]


class CatalogueViewOut(ApiModel):
    product_catalogue_view: CatalogueView
    updated_at: datetime | None
    revision: int = Field(ge=0)


class CatalogueViewWrite(ApiModel):
    """The signed-in cashier's own catalogue view. A client timestamp is only for sync."""

    product_catalogue_view: CatalogueView
    updated_at: datetime | None = None
