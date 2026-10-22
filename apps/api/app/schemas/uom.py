from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel, UnitOption


class UnitOut(UnitOption):
    id: UUID | None
    is_system: bool
    is_active: bool
    products: int


class UnitCreate(ApiModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=2, max_length=60)
    short_name: str = Field(min_length=1, max_length=16)
    factor: int = Field(ge=2, le=100_000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        code = "_".join(value.strip().upper().replace("-", " ").split())
        if not code or not code[0].isalpha() or not all(char.isalnum() or char == "_" for char in code):
            raise ValueError("Use letters, digits and underscores, starting with a letter (e.g. CASE_24).")
        return code

    @field_validator("name", "short_name")
    @classmethod
    def trim(cls, value: str) -> str:
        return " ".join(value.split())


class UnitUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    short_name: str | None = Field(default=None, min_length=1, max_length=16)
    is_active: bool | None = None
