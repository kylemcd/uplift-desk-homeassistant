"""State coordinator for an UPLIFT desk transport."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeskApi, DeskApiError, DeskCommandError
from .const import CONF_VIRTUAL_PRESETS, DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class UpliftDeskCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Refresh desk state and update immediately after commands."""

    def __init__(
        self, hass: HomeAssistant, api: DeskApi, entry: ConfigEntry
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.api = api
        self.entry = entry
        self.virtual_presets = {
            str(name): float(height)
            for name, height in entry.options.get(CONF_VIRTUAL_PRESETS, {}).items()
        }
        self.selected_virtual_preset = next(iter(self.virtual_presets), None)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_state()
        except DeskApiError as error:
            raise UpdateFailed(str(error)) from error

    async def async_execute(self, command: Callable[[], Awaitable[None]]) -> None:
        """Execute a broker operation and immediately refresh entity state."""
        await command()
        await self.async_request_refresh()

    @callback
    def select_virtual_preset(self, name: str) -> None:
        """Select an existing virtual preset and load it into the editor."""
        if name not in self.virtual_presets:
            raise DeskCommandError(f"Virtual preset {name!r} does not exist")
        self.selected_virtual_preset = name
        self.async_update_listeners()

    async def async_recall_virtual_preset(self) -> None:
        """Move the desk to the selected Home Assistant virtual preset."""
        name = self.selected_virtual_preset
        if name is None:
            raise DeskCommandError("No virtual preset is selected")
        await self.async_recall_virtual_preset_named(name)

    async def async_recall_virtual_preset_named(self, name: str) -> None:
        """Move the desk to a named Home Assistant virtual preset."""
        if name not in self.virtual_presets:
            raise DeskCommandError(f"Virtual preset {name!r} does not exist")
        height_mm = self.virtual_presets[name]
        self._validate_height(height_mm)

        async def recall() -> None:
            await self.api.async_set_target_height(height_mm)
            await self.api.async_move_to_target()

        await self.async_execute(recall)

    def _validate_height(self, height_mm: float) -> None:
        minimum = self.data.get("minimumMm") if self.data else None
        maximum = self.data.get("maximumMm") if self.data else None
        if minimum is None or maximum is None:
            raise DeskCommandError("Desk height limits are not known")
        if not float(minimum) <= height_mm <= float(maximum):
            raise DeskCommandError("Virtual preset height is outside the desk limits")
