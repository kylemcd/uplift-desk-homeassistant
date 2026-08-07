"""UPLIFT Desk Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BluetoothBrokerApi, DeskApiError
from .bluetooth import BluetoothDeskApi
from .const import (
    CONF_BROKER_URL,
    CONF_CONNECTION_TYPE,
    CONF_DESK_ID,
    CONNECTION_BLUETOOTH,
    CONNECTION_BROKER,
    PLATFORMS,
)
from .coordinator import UpliftDeskCoordinator

type UpliftDeskConfigEntry = ConfigEntry[UpliftDeskCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: UpliftDeskConfigEntry) -> bool:
    """Set up UPLIFT Desk from a config entry."""
    if entry.data[CONF_CONNECTION_TYPE] == CONNECTION_BLUETOOTH:
        api = BluetoothDeskApi(
            hass,
            entry.data["address"],
            entry.data.get("name", entry.title),
        )
    else:
        api = BluetoothBrokerApi(
            async_get_clientsession(hass),
            entry.data[CONF_BROKER_URL],
            entry.data[CONF_DESK_ID],
        )
    coordinator = UpliftDeskCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    _remove_legacy_preset_editor_entities(hass, entry, coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _remove_legacy_preset_editor_entities(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    coordinator: UpliftDeskCoordinator,
) -> None:
    """Remove the entity-based preset editor replaced by the options form."""
    address = str(coordinator.data.get("address", "unknown"))
    legacy_unique_ids = {
        f"{address}_{key}".lower().replace(":", "")
        for key in (
            "capture_virtual_preset_height",
            "delete_virtual_preset",
            "save_virtual_preset",
            "virtual_preset_height",
            "virtual_preset_name",
        )
    }
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id in legacy_unique_ids:
            registry.async_remove(registry_entry.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: UpliftDeskConfigEntry) -> bool:
    """Unload an UPLIFT Desk config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.api.async_close()
    return unload_ok


async def async_migrate_entry(
    hass: HomeAssistant, entry: UpliftDeskConfigEntry
) -> bool:
    """Migrate broker-only 0.2.x entries to the transport-aware schema."""
    if entry.version >= 2:
        return True
    broker_url = entry.data.get(CONF_BROKER_URL)
    if not broker_url:
        return False
    api = BluetoothBrokerApi(async_get_clientsession(hass), broker_url, "")
    try:
        desks = await api.async_desks()
    except DeskApiError:
        return False
    if not desks or not desks[0].get("id"):
        return False
    hass.config_entries.async_update_entry(
        entry,
        data={
            CONF_CONNECTION_TYPE: CONNECTION_BROKER,
            CONF_BROKER_URL: broker_url,
            CONF_DESK_ID: str(desks[0]["id"]),
        },
        version=2,
    )
    return True
