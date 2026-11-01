"""Compatibility imports. Campaign logic lives in the Reach plugin."""

from app.services.reach_bridge import channel_enabled, record_usage

__all__ = ["channel_enabled", "record_usage"]
