"""Diagnostics support for UPLIFT Desk."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import UpliftDeskConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: UpliftDeskConfigEntry
) -> dict[str, Any]:
    """Return broker and desk state without credentials."""
    return {
        "entry": {"title": entry.title, "version": entry.version},
        "broker_url": entry.runtime_data.api.base_url,
        "desk": entry.runtime_data.data,
    }
