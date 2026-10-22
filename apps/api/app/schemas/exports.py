from pydantic import Field

from app.schemas.payloads import ApiModel


class GlAccountOut(ApiModel):
    key: str
    use: str
    code: str
    name: str
    default_code: str
    default_name: str


class GlAccountEntry(ApiModel):
    # Blank keeps the default.
    code: str = Field(default="", max_length=20, pattern=r"^[A-Za-z0-9.\-]*$")
    name: str = Field(default="", max_length=80)


class GlAccountsWrite(ApiModel):
    accounts: dict[str, GlAccountEntry] = Field(max_length=80)
