"""Mounts Delivery Integrations. A missing package must not stop the rest of the API."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter

log = logging.getLogger("ai-pos.delivery")
_ROOT = Path(__file__).resolve().parents[5] / "plugins" / "delivery"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from delivery.router import router
except Exception:
    log.warning("Delivery Integrations plugin is not installed; /api/v1/delivery is off")
    router = APIRouter()
