"""Compatibility imports. Request models live in the Reach plugin."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4] / "plugins" / "reach"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from reach.schemas import (  # noqa: E402
    CampaignOut,
    CampaignWrite,
    ChannelOut,
    ChannelWrite,
    ConnectionCreate,
    ConnectionOut,
    CreditAllocate,
    CreditOut,
    CreditTransactionOut,
    OverviewOut,
    PreviewOut,
    PricesWrite,
    RecipientOut,
    TemplateOut,
    TemplateWrite,
)

__all__ = [
    "CampaignOut",
    "CampaignWrite",
    "ChannelOut",
    "ChannelWrite",
    "ConnectionCreate",
    "ConnectionOut",
    "CreditAllocate",
    "CreditOut",
    "CreditTransactionOut",
    "OverviewOut",
    "PreviewOut",
    "PricesWrite",
    "RecipientOut",
    "TemplateOut",
    "TemplateWrite",
]
