from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

TicketStatus = Literal["NEW", "PREPARING", "READY", "BUMPED"]


class KitchenStationIn(ApiModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=40)
    category_ids: list[UUID] = Field(default_factory=list, max_length=200)
    is_default: bool = False
    print_tickets: bool = False
    position: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class KitchenStationOut(KitchenStationIn):
    id: UUID


class TicketItemOut(ApiModel):
    id: UUID
    order_item_id: UUID | None
    product_name: str
    quantity: int
    modifiers: list[dict] = Field(default_factory=list)
    combo_name: str | None = None
    seat: int | None
    note: str | None
    voided_at: datetime | None


class TicketOut(ApiModel):
    id: UUID
    station_id: UUID
    station_name: str
    # The sending register prints this ticket (the station has no screen, or wants paper too).
    print_tickets: bool = False
    order_id: UUID | None
    sale_id: UUID | None
    number: int
    label: str
    service_type: str
    status: TicketStatus
    fired_at: datetime
    started_at: datetime | None
    ready_at: datetime | None
    bumped_at: datetime | None
    updated_at: datetime
    items: list[TicketItemOut]


class TicketBoard(ApiModel):
    # Pass server_time back as `since` on the next poll to get only what changed.
    server_time: datetime
    station: KitchenStationOut
    # Ticket age (minutes) at which the screen turns a ticket amber, then red.
    warn_minutes: int
    late_minutes: int
    tickets: list[TicketOut]


class TicketStatusIn(ApiModel):
    status: TicketStatus
