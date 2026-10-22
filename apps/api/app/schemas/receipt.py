"""Receipt branding, stored as one JSON document on business_settings.receipt."""

import base64
import binascii
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

LOGO_PREFIX = "data:image/png;base64,"
LOGO_MAX_BYTES = 64 * 1024
# 576 dots is the printable width of 80 mm paper; taller logos waste paper on every receipt.
LOGO_MAX_WIDTH = 576
LOGO_MAX_HEIGHT = 320
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = "\n".join(line.rstrip() for line in value.strip().splitlines())
    return cleaned or None


class ReceiptSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Black-and-white PNG as a data URL, small enough to cache on every register for offline printing.
    logo_png: str | None = Field(default=None, max_length=len(LOGO_PREFIX) + (LOGO_MAX_BYTES * 4) // 3 + 4)
    header_text: str | None = Field(default=None, max_length=200)
    header_text_ar: str | None = Field(default=None, max_length=200)
    footer_text: str | None = Field(default=None, max_length=500)
    footer_text_ar: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=120, pattern=r"^\s*([^@\s]+@[^@\s]+\.[^@\s]+)?\s*$")
    website: str | None = Field(default=None, max_length=120)

    @field_validator("header_text", "header_text_ar", "footer_text", "footer_text_ar", "email", "website")
    @classmethod
    def tidy(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("logo_png")
    @classmethod
    def small_png(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        if not value.startswith(LOGO_PREFIX):
            raise ValueError("The logo must be a PNG image.")
        try:
            raw = base64.b64decode(value[len(LOGO_PREFIX) :], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("The logo is not valid base64.") from exc
        if len(raw) > LOGO_MAX_BYTES:
            raise ValueError(f"The logo must be at most {LOGO_MAX_BYTES // 1024} KB.")
        if len(raw) < 24 or not raw.startswith(_PNG_SIGNATURE) or raw[12:16] != b"IHDR":
            raise ValueError("The logo must be a PNG image.")
        width = int.from_bytes(raw[16:20], "big")
        height = int.from_bytes(raw[20:24], "big")
        if not (0 < width <= LOGO_MAX_WIDTH and 0 < height <= LOGO_MAX_HEIGHT):
            raise ValueError(f"The logo must fit in {LOGO_MAX_WIDTH} x {LOGO_MAX_HEIGHT} pixels.")
        return value


class ReceiptStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None


class ReceiptProfileOut(BaseModel):
    """Everything a register prints at the top and bottom of a slip, besides the tax identity in /settings."""

    model_config = ConfigDict(extra="forbid")

    settings: ReceiptSettings
    store: ReceiptStore | None = None


def resolve_receipt_settings(raw: dict | None) -> ReceiptSettings:
    """Stored settings, or the defaults when nothing (or something no longer valid) is stored."""
    if not raw:
        return ReceiptSettings()
    try:
        return ReceiptSettings.model_validate(raw)
    except ValueError:
        return ReceiptSettings()
