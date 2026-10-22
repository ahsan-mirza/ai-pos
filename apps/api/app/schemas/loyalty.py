from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from app.schemas.payloads import ApiModel


class LoyaltyTier(ApiModel):
    name: str = Field(min_length=1, max_length=40)
    # Paid spend over the last 12 months, in minor units, needed to reach the tier.
    min_spend_cents: int = Field(ge=0, le=10_000_000_000)
    # Earn rate as a percentage of the base rate: 150 earns one and a half times the points.
    multiplier_pct: int = Field(ge=100, le=1000)


class LoyaltySettingsWrite(ApiModel):
    enabled: bool
    # Points earned per whole unit of the business currency paid.
    earn_per_unit: int = Field(ge=0, le=1000)
    # Value of one point in the business currency's minor units.
    redeem_cents: int = Field(ge=1, le=10_000)
    min_redeem: int = Field(ge=1, le=1_000_000)
    # Points lapse this many months after they are earned (oldest first); 0 keeps them forever.
    expiry_months: int = Field(default=0, ge=0, le=120)
    tiers: list[LoyaltyTier] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def ordered_tiers(self) -> Self:
        thresholds = [tier.min_spend_cents for tier in self.tiers]
        if thresholds != sorted(thresholds) or len(set(thresholds)) != len(thresholds):
            raise ValueError("Tiers must have distinct spend thresholds, lowest first.")
        if len({tier.name.strip().lower() for tier in self.tiers}) != len(self.tiers):
            raise ValueError("Tier names must be unique.")
        return self


class LoyaltySettingsOut(LoyaltySettingsWrite):
    pass


class LoyaltyEntryOut(ApiModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    entry_type: str
    points: int
    balance_after: int
    sale_id: UUID | None
    return_id: UUID | None
    note: str
    created_at: datetime


class LoyaltyAdjust(ApiModel):
    points: int = Field(ge=-1_000_000, le=1_000_000)
    note: str = Field(min_length=3, max_length=255)


class LoyaltyStanding(ApiModel):
    points: int
    tier: str | None
    multiplier_pct: int
    spend_12m_cents: int
    next_tier: str | None
    next_tier_gap_cents: int | None
    # Points that lapse within 30 days unless spent.
    expiring_soon: int
    entries: list[LoyaltyEntryOut]
