"""Mounts the AxizReach plugin. A missing package must not stop the rest of the API."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from fastapi import APIRouter

log = logging.getLogger("ai-pos.reach")
_ROOT = Path(__file__).resolve().parents[5] / "plugins" / "reach"
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from reach.router import router
except Exception:
    log.warning("AxizReach plugin is not installed; /api/v1/reach is off")
    router = APIRouter()
