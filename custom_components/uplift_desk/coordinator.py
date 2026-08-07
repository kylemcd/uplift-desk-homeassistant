"""State coordinator for an UPLIFT desk transport."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeskApi, DeskApiError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class UpliftDeskCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Refresh desk state and update immediately after commands."""

    def __init__(self, hass: HomeAssistant, api: DeskApi) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.api.async_state()
        except DeskApiError as error:
            raise UpdateFailed(str(error)) from error

    async def async_execute(self, command: Callable[[], Awaitable[None]]) -> None:
        """Execute a broker operation and immediately refresh entity state."""
        await command()
        await self.async_request_refresh()
