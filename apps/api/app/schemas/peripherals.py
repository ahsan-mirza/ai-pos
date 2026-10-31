from datetime import datetime
from typing import Literal

from app.schemas.payloads import ApiModel

Light = Literal["green", "red", "gray", "amber"]
Kind = Literal["kds", "table_apps", "customer_display", "card_terminal"]


class PeripheralOut(ApiModel):
    id: str
    kind: Kind
    label: str
    name: str
    light: Light
    status: str
    connection: str
    last_seen_at: datetime | None = None
    last_ok_at: datetime | None = None
    last_error: str | None = None
    address: str | None = None
    pending: int | None = None
    connected: int | None = None
    configured: int | None = None


class PeripheralSnapshot(ApiModel):
    items: list[PeripheralOut]
