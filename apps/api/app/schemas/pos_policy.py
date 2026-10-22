"""Till rules for the whole business, stored as one JSON document on business_settings.pos_policy: cashier discounts,
gift cards, and the returns policy. Registers cache it with the business settings so the rules hold offline."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

KEY_PATTERN = r"^[a-z][a-z0-9_]{1,31}$"


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Choice(_Section):
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=60)


class DiscountPolicy(_Section):
    reasons: list[Choice] = Field(
        default_factory=lambda: [
            Choice(key="staff", label="Staff discount"),
            Choice(key="damaged", label="Damaged or soiled item"),
            Choice(key="vip", label="VIP customer"),
            Choice(key="price_match", label="Price match"),
            Choice(key="other", label="Other"),
        ],
        min_length=1,
        max_length=20,
    )
    # Largest discount (basis points of a line) a cashier with pos:discount gives alone when their role sets no limit.
    default_limit_bps: int = Field(default=1000, ge=0, le=10_000)

    @field_validator("reasons")
    @classmethod
    def unique(cls, value: list[Choice]) -> list[Choice]:
        if len({choice.key for choice in value}) != len(value):
            raise ValueError("Discount reason keys must be unique.")
        return value


class GiftCardPolicy(_Section):
    # Months a card stays valid from the day it is sold; None never expires.
    expiry_months: int | None = Field(default=36, ge=1, le=120)
    min_cents: int = Field(default=1000, ge=100, le=10_000_000)
    max_cents: int = Field(default=500_000, ge=100, le=100_000_000)

    @model_validator(mode="after")
    def ordered(self) -> "GiftCardPolicy":
        if self.max_cents < self.min_cents:
            raise ValueError("The largest gift card must be at least the smallest.")
        return self


class ReturnCondition(_Section):
    key: str = Field(pattern=KEY_PATTERN)
    label: str = Field(min_length=1, max_length=60)
    # Goes back on the shelf as sellable stock.
    restock: bool = True
    # Restocking fee kept, basis points of the refunded line.
    fee_bps: int = Field(default=0, ge=0, le=5000)
    # Serialized units: where the returned unit goes (in_stock, quarantine, repair).
    serial_status: Literal["in_stock", "quarantine", "repair"] = "in_stock"


ELECTRONICS_CONDITIONS = [
    ReturnCondition(key="unopened_resealable", label="Unopened / resealable", restock=True, serial_status="in_stock"),
    ReturnCondition(key="open_box", label="Open box", restock=False, fee_bps=1500, serial_status="quarantine"),
    ReturnCondition(key="defective_doa", label="Defective / DOA", restock=False, serial_status="repair"),
]
FASHION_CONDITIONS = [
    ReturnCondition(key="tags_attached", label="Tags attached, unworn", restock=True),
    ReturnCondition(key="worn", label="Worn or washed", restock=False, serial_status="quarantine"),
    ReturnCondition(key="damaged", label="Damaged or faulty", restock=False, serial_status="repair"),
]
BASE_REASONS = [
    Choice(key="defective", label="Defective"),
    Choice(key="changed_mind", label="Changed mind"),
    Choice(key="wrong_item", label="Wrong item"),
    Choice(key="damaged_in_transit", label="Damaged in transit"),
    Choice(key="not_as_described", label="Not as described"),
    Choice(key="other", label="Other"),
]
FASHION_REASONS = [
    Choice(key="size_fit", label="Size or fit"),
    Choice(key="style", label="Style or colour"),
    Choice(key="quality", label="Quality"),
    *BASE_REASONS,
]


class ReturnsPolicy(_Section):
    preset: Literal["electronics", "fashion", "custom"] = "electronics"
    # Refunds to the original tender within this many days of the sale.
    window_days: int = Field(default=30, ge=0, le=365)
    # Further days after the refund window when the return is accepted as an exchange voucher only.
    exchange_window_days: int = Field(default=0, ge=0, le=365)
    conditions: list[ReturnCondition] = Field(
        default_factory=lambda: list(ELECTRONICS_CONDITIONS), min_length=1, max_length=10
    )
    reasons: list[Choice] = Field(default_factory=lambda: list(BASE_REASONS), min_length=1, max_length=20)

    @field_validator("conditions")
    @classmethod
    def unique_conditions(cls, value: list[ReturnCondition]) -> list[ReturnCondition]:
        if len({condition.key for condition in value}) != len(value):
            raise ValueError("Return condition keys must be unique.")
        return value

    def condition(self, key: str) -> ReturnCondition | None:
        return next((condition for condition in self.conditions if condition.key == key), None)


def returns_preset(name: Literal["electronics", "fashion"]) -> ReturnsPolicy:
    if name == "fashion":
        return ReturnsPolicy(
            preset="fashion",
            window_days=14,
            exchange_window_days=16,
            conditions=list(FASHION_CONDITIONS),
            reasons=list(FASHION_REASONS),
        )
    return ReturnsPolicy()


class PosPolicy(_Section):
    discounts: DiscountPolicy = Field(default_factory=DiscountPolicy)
    gift_cards: GiftCardPolicy = Field(default_factory=GiftCardPolicy)
    returns: ReturnsPolicy = Field(default_factory=ReturnsPolicy)


FASHION_PROFILES = frozenset({"retail_fashion"})


def resolve_pos_policy(raw: dict | None, profile: str | None = None) -> PosPolicy:
    """Stored policy with defaults filled in. A business that never set a returns policy gets its business type's
    preset (fashion rules for a fashion store); an invalid stored section falls back to its default."""
    raw = raw or {}
    sections: dict[str, object] = {}
    for name, field in PosPolicy.model_fields.items():
        value = raw.get(name)
        if value is None:
            continue
        try:
            sections[name] = field.annotation.model_validate(value)  # type: ignore[union-attr]
        except ValueError:
            continue
    if "returns" not in sections and profile in FASHION_PROFILES:
        sections["returns"] = returns_preset("fashion")
    return PosPolicy(**sections)  # type: ignore[arg-type]
