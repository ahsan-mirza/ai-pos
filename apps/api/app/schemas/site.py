from pydantic import Field

from app.schemas.payloads import ApiModel


class SiteContactOut(ApiModel):
    whatsapp: str


class SiteContactIn(ApiModel):
    whatsapp: str = Field(default="", max_length=32)
    reason: str = Field(min_length=3, max_length=500)
