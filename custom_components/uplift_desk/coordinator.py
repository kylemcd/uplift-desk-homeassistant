"""State coordinator for an UPLIFT desk transport."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
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
        self.virtual_preset_name = self.selected_virtual_preset or ""
        self.virtual_preset_height_mm = (
            self.virtual_presets.get(self.selected_virtual_preset)
            if self.selected_virtual_preset
            else None
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            state = await self.api.async_state()
            if self.virtual_preset_height_mm is None:
                initial_height = (
                    state.get("targetHeightMm")
                    or state.get("heightMm")
                    or state.get("minimumMm")
                )
                if initial_height is not None:
                    self.virtual_preset_height_mm = float(initial_height)
            return state
        except DeskApiError as error:
            raise UpdateFailed(str(error)) from error

    async def async_execute(self, command: Callable[[], Awaitable[None]]) -> None:
        """Execute a broker operation and immediately refresh entity state."""
        await command()
        await self.async_request_refresh()

    @callback
    def set_virtual_preset_name(self, name: str) -> None:
        """Stage the name used by the next virtual-preset save."""
        self.virtual_preset_name = name
        self.async_update_listeners()

    @callback
    def set_virtual_preset_height(self, height_mm: float) -> None:
        """Stage the height used by the next virtual-preset save."""
        self._validate_height(height_mm)
        self.virtual_preset_height_mm = height_mm
        self.async_update_listeners()

    async def async_capture_current_height(self) -> None:
        """Copy the latest desk height into the virtual-preset editor."""
        height = self.data.get("heightMm") if self.data else None
        if height is None:
            raise DeskCommandError("Current desk height is not known")
        self.set_virtual_preset_height(float(height))

    @callback
    def select_virtual_preset(self, name: str) -> None:
        """Select an existing virtual preset and load it into the editor."""
        if name not in self.virtual_presets:
            raise DeskCommandError(f"Virtual preset {name!r} does not exist")
        self.selected_virtual_preset = name
        self.virtual_preset_name = name
        self.virtual_preset_height_mm = self.virtual_presets[name]
        self.async_update_listeners()

    async def async_save_virtual_preset(self) -> None:
        """Persist the staged name and height in the Home Assistant config entry."""
        name = " ".join(self.virtual_preset_name.split())
        if not name:
            raise DeskCommandError("Virtual preset name cannot be empty")
        if len(name) > 64:
            raise DeskCommandError("Virtual preset name cannot exceed 64 characters")
        if self.virtual_preset_height_mm is None:
            raise DeskCommandError("Virtual preset height has not been set")
        self._validate_height(self.virtual_preset_height_mm)
        self.virtual_presets[name] = self.virtual_preset_height_mm
        self.selected_virtual_preset = name
        self.virtual_preset_name = name
        self._persist_virtual_presets()

    async def async_recall_virtual_preset(self) -> None:
        """Move the desk to the selected Home Assistant virtual preset."""
        name = self.selected_virtual_preset
        if name is None or name not in self.virtual_presets:
            raise DeskCommandError("No virtual preset is selected")
        height_mm = self.virtual_presets[name]
        self._validate_height(height_mm)

        async def recall() -> None:
            await self.api.async_set_target_height(height_mm)
            await self.api.async_move_to_target()

        await self.async_execute(recall)

    async def async_delete_virtual_preset(self) -> None:
        """Delete the selected Home Assistant virtual preset."""
        name = self.selected_virtual_preset
        if name is None or name not in self.virtual_presets:
            raise DeskCommandError("No virtual preset is selected")
        del self.virtual_presets[name]
        self.selected_virtual_preset = next(iter(self.virtual_presets), None)
        self.virtual_preset_name = self.selected_virtual_preset or ""
        self.virtual_preset_height_mm = (
            self.virtual_presets.get(self.selected_virtual_preset)
            if self.selected_virtual_preset
            else self.data.get("heightMm")
        )
        self._persist_virtual_presets()

    @callback
    def _persist_virtual_presets(self) -> None:
        options = dict(self.entry.options)
        options[CONF_VIRTUAL_PRESETS] = dict(self.virtual_presets)
        self.hass.config_entries.async_update_entry(self.entry, options=options)
        self.async_update_listeners()

    def _validate_height(self, height_mm: float) -> None:
        minimum = self.data.get("minimumMm") if self.data else None
        maximum = self.data.get("maximumMm") if self.data else None
        if minimum is None or maximum is None:
            raise DeskCommandError("Desk height limits are not known")
        if not float(minimum) <= height_mm <= float(maximum):
            raise DeskCommandError("Virtual preset height is outside the desk limits")
