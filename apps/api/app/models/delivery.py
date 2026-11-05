"""Re-export Delivery Integrations models. A missing package must not stop the API."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger("ai-pos.delivery")
_ROOT = Path(__file__).resolve().parents[4] / "plugins" / "delivery"
if _ROOT.is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from delivery.models import DeliveryConnection
except ModuleNotFoundError:
    log.warning("Delivery Integrations plugin is not installed; its models are not registered")
    DeliveryConnection = None  # type: ignore[misc, assignment]
