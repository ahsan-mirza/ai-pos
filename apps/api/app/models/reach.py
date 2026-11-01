"""Re-export Reach models so the API metadata registry stays in core. Logic lives in the plugin."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4] / "plugins" / "reach"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from reach.models import (  # noqa: E402
    MessagingChannel,
    ReachCampaign,
    ReachConnection,
    ReachCreditAccount,
    ReachCreditTransaction,
    ReachRecipient,
    ReachTemplate,
    ReachUsage,
    ReachWebhookEvent,
)

__all__ = [
    "MessagingChannel",
    "ReachCampaign",
    "ReachConnection",
    "ReachCreditAccount",
    "ReachCreditTransaction",
    "ReachRecipient",
    "ReachTemplate",
    "ReachUsage",
    "ReachWebhookEvent",
]
