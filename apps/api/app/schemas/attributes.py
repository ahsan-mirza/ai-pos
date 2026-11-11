from uuid import UUID

from pydantic import Field

from app.schemas.batches import ApiModel

AttributeType = str


class AttributeOut(ApiModel):
    id: UUID
    key: str
    name: str
    description: str
    data_type: str
    unit: str
    options: list[str]
    required: bool
    searchable: bool
    filterable: bool
    active: bool
    sort_order: int
    origin: str


class AttributeCreate(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    key: str | None = Field(default=None, max_length=32)
    data_type: str = "text"
    unit: str = ""
    options: list[str] = Field(default_factory=list, max_length=40)
    description: str = ""
    required: bool = False
    searchable: bool = False
    filterable: bool = False


class AttributeUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = None
    data_type: str | None = None
    unit: str | None = None
    options: list[str] | None = None
    required: bool | None = None
    searchable: bool | None = None
    filterable: bool | None = None
    active: bool | None = None
    sort_order: int | None = None


def attribute_out(row) -> AttributeOut:
    return AttributeOut(
        id=row.id,
        key=row.key,
        name=row.name,
        description=row.description,
        data_type=row.data_type,
        unit=row.unit,
        options=list(row.options or []),
        required=row.required,
        searchable=row.searchable,
        filterable=row.filterable,
        active=row.active,
        sort_order=row.sort_order,
        origin=row.origin,
    )
