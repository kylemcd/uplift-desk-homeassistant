"""Binary sensors for an UPLIFT desk."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up desk binary sensors."""
    registry = er.async_get(hass)
    address = str(entry.runtime_data.data.get("address", "unknown"))
    legacy_prefix = f"{address}_presence_".lower().replace(":", "")
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.unique_id.startswith(legacy_prefix):
            registry.async_remove(registry_entry.entity_id)
    async_add_entities(
        [
            UpliftConnectedSensor(entry.runtime_data),
            UpliftResetRequiredSensor(entry.runtime_data),
        ]
    )


class UpliftConnectedSensor(UpliftDeskEntity, BinarySensorEntity):
    _attr_name = "Connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "connected")

    @property
    def is_on(self) -> bool:
        return bool(self.state_data.get("connected"))


class UpliftResetRequiredSensor(UpliftDeskEntity, BinarySensorEntity):
    _attr_name = "Reset required"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_required")

    @property
    def is_on(self) -> bool:
        return bool(self.state_data.get("resetRequired"))
