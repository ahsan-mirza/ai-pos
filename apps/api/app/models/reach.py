"""Re-export Reach models so the API metadata registry stays in core. Logic lives in the plugin.

A server without plugins/reach still boots. Campaign features stay off until that package is installed.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("ai-pos.reach")
_ROOT = Path(__file__).resolve().parents[4] / "plugins" / "reach"
if _ROOT.is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from reach.models import (  # noqa: E402
        MessagingChannel,
        ReachCampaign,
        ReachCampaignSuggestion,
        ReachConnection,
        ReachCreditAccount,
        ReachCreditTransaction,
        ReachMediaAsset,
        ReachRecipient,
        ReachTemplate,
        ReachUsage,
        ReachWebhookEvent,
    )
except ModuleNotFoundError:
    log.warning("AxizReach plugin is not installed; Reach models are not registered")
    MessagingChannel = None  # type: ignore[misc, assignment]
    ReachCampaign = None  # type: ignore[misc, assignment]
    ReachConnection = None  # type: ignore[misc, assignment]
    ReachCreditAccount = None  # type: ignore[misc, assignment]
    ReachCreditTransaction = None  # type: ignore[misc, assignment]
    ReachRecipient = None  # type: ignore[misc, assignment]
    ReachTemplate = None  # type: ignore[misc, assignment]
    ReachUsage = None  # type: ignore[misc, assignment]
    ReachWebhookEvent = None  # type: ignore[misc, assignment]
    ReachMediaAsset = None  # type: ignore[misc, assignment]
    ReachCampaignSuggestion = None  # type: ignore[misc, assignment]

__all__ = [
    "MessagingChannel",
    "ReachCampaign",
    "ReachCampaignSuggestion",
    "ReachConnection",
    "ReachCreditAccount",
    "ReachCreditTransaction",
    "ReachMediaAsset",
    "ReachRecipient",
    "ReachTemplate",
    "ReachUsage",
    "ReachWebhookEvent",
]
