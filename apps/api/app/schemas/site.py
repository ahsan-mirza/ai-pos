from pydantic import Field

from app.schemas.payloads import ApiModel


class SiteContactOut(ApiModel):
    """Public click-to-chat settings. Nothing here is an admin secret."""

    enabled: bool
    # Digits with the country code, without a leading plus, or blank.
    whatsapp: str
    message: str
    tooltip: str
    # Public sales address shown in the site footer, or blank.
    email: str = ""


class SiteContactIn(ApiModel):
    enabled: bool = True
    whatsapp: str = Field(default="", max_length=40)
    message: str = Field(default="", max_length=500)
    tooltip: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=254)
    reason: str = Field(min_length=3, max_length=500)
