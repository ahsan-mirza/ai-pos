"""Configuration of the optional modules, stored as one JSON document on business_settings.module_settings."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FefoSettings(_Section):
    # Batches expiring within this many days show on the Expiring stock report and in the daily alert.
    alert_days: int = Field(default=14, ge=1, le=365)


class EmbeddedBarcodeSettings(_Section):
    """EAN-13 labels printed by a scale: prefix (2 digits) + PLU + value + check digit."""

    prefixes: list[str] = Field(default_factory=lambda: [str(n) for n in range(20, 30)], max_length=10)
    # "weight": the value is grams (the label prices at the per-kg price); "price": the value is the line price.
    mode: Literal["weight", "price"] = "weight"
    plu_length: int = Field(default=5, ge=4, le=6)

    @field_validator("prefixes")
    @classmethod
    def two_digits(cls, value: list[str]) -> list[str]:
        cleaned = sorted({item.strip() for item in value if item.strip()})
        if any(len(item) != 2 or not item.isdigit() for item in cleaned):
            raise ValueError("Barcode prefixes are two digits, e.g. 20 to 29.")
        return cleaned


class WeighedItemsSettings(_Section):
    embedded_barcodes: EmbeddedBarcodeSettings = Field(default_factory=EmbeddedBarcodeSettings)


class ServiceChargeSettings(_Section):
    # Basis points of the bill before tax; 0 turns the automatic service charge off.
    service_charge_bps: int = Field(default=0, ge=0, le=3000)
    service_charge_taxable: bool = True
    # Apply only to dine-in orders, and only from this many covers (0 = any table).
    dine_in_only: bool = True
    min_covers: int = Field(default=0, ge=0, le=100)
    # Quick tip buttons on the payment screen, in basis points of the bill.
    tip_presets_bps: list[int] = Field(default_factory=lambda: [1000, 1500, 2000], max_length=4)

    @field_validator("tip_presets_bps")
    @classmethod
    def sane_presets(cls, value: list[int]) -> list[int]:
        if any(item <= 0 or item > 5000 for item in value):
            raise ValueError("Tip presets are between 0.01% and 50%.")
        return sorted(set(value))


class KdsSettings(_Section):
    # Ticket age (minutes) at which a kitchen ticket turns amber, then red.
    warn_minutes: int = Field(default=8, ge=1, le=120)
    late_minutes: int = Field(default=15, ge=2, le=240)


class RepairSettings(_Section):
    # Our guarantee on the parts and labour of an invoiced repair (0 = none).
    warranty_days: int = Field(default=90, ge=0, le=730)
    # How long the customer's estimate-approval link stays valid.
    approval_link_hours: int = Field(default=72, ge=1, le=720)
    # Suggested deposit at intake, in basis points of the estimate (0 = no deposit asked).
    deposit_bps: int = Field(default=0, ge=0, le=10_000)
    # Printed on the job card the customer signs at intake.
    terms: str = Field(
        default=(
            "We are not responsible for data loss; back up your device before repair. Devices not collected within "
            "90 days of the ready message may be disposed of. Repairs carry the warranty shown on the invoice."
        ),
        max_length=2000,
    )


class BagSettings(_Section):
    """A cashier adds bags from the till. Nothing here is applied on its own."""

    enabled: bool = False
    fee_cents: int = Field(default=0, ge=0, le=100_000)
    tax_category: Literal["STANDARD", "ZERO", "EXEMPT"] = "STANDARD"


class DepartmentKey(_Section):
    category_id: UUID
    label: str = Field(min_length=1, max_length=40)


class DepartmentKeysSettings(_Section):
    keys: list[DepartmentKey] = Field(default_factory=list, max_length=16)

    @field_validator("keys")
    @classmethod
    def unique_categories(cls, value: list[DepartmentKey]) -> list[DepartmentKey]:
        seen: set[UUID] = set()
        for key in value:
            if key.category_id in seen:
                raise ValueError("Each department key uses a different category.")
            seen.add(key.category_id)
        return value


class ModuleSettings(_Section):
    fefo: FefoSettings = Field(default_factory=FefoSettings)
    weighed_items: WeighedItemsSettings = Field(default_factory=WeighedItemsSettings)
    tips_service_charge: ServiceChargeSettings = Field(default_factory=ServiceChargeSettings)
    kds: KdsSettings = Field(default_factory=KdsSettings)
    repairs: RepairSettings = Field(default_factory=RepairSettings)
    bags: BagSettings = Field(default_factory=BagSettings)
    department_keys: DepartmentKeysSettings = Field(default_factory=DepartmentKeysSettings)


def resolve_module_settings(raw: dict | None) -> ModuleSettings:
    """Stored settings with defaults filled in; unknown or invalid stored sections fall back to their defaults."""
    if not raw:
        return ModuleSettings()
    sections: dict[str, object] = {}
    for name, field in ModuleSettings.model_fields.items():
        value = raw.get(name)
        if value is None:
            continue
        try:
            sections[name] = field.annotation.model_validate(value)  # type: ignore[union-attr]
        except ValueError:
            continue
    return ModuleSettings(**sections)  # type: ignore[arg-type]
