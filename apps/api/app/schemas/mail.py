from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel

MailSecurity = Literal["ssl", "starttls", "none"]


class MailSettingsOut(ApiModel):
    enabled: bool
    host: str
    port: int
    security: MailSecurity
    username: str
    password_set: bool
    from_address: str
    from_name: str


class MailSettingsIn(ApiModel):
    enabled: bool
    host: str = Field(default="", max_length=255)
    port: int = Field(default=465, ge=1, le=65535)
    security: MailSecurity = "ssl"
    username: str = Field(default="", max_length=254)
    # Blank keeps the password already stored.
    password: str = Field(default="", max_length=256)
    from_address: str = Field(default="", max_length=254)
    from_name: str = Field(default="AI POS", max_length=120)
    reason: str = Field(min_length=3, max_length=500)


class MailTestIn(ApiModel):
    to: str = Field(min_length=3, max_length=254)


class MailTestOut(ApiModel):
    sent: bool = True
