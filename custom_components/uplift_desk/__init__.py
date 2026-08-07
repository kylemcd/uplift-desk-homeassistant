"""UPLIFT Desk Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BluetoothBrokerApi
from .const import CONF_BROKER_URL, PLATFORMS
from .coordinator import UpliftDeskCoordinator

type UpliftDeskConfigEntry = ConfigEntry[UpliftDeskCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: UpliftDeskConfigEntry) -> bool:
    """Set up UPLIFT Desk from a config entry."""
    api = BluetoothBrokerApi(async_get_clientsession(hass), entry.data[CONF_BROKER_URL])
    coordinator = UpliftDeskCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: UpliftDeskConfigEntry) -> bool:
    """Unload an UPLIFT Desk config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
