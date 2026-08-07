"""Virtual-preset naming for an UPLIFT desk."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the virtual-preset name editor."""
    async_add_entities([UpliftVirtualPresetName(entry.runtime_data)])


class UpliftVirtualPresetName(UpliftDeskEntity, TextEntity):
    """Stage the name used by the next virtual-preset save."""

    _attr_name = "Virtual preset name"
    _attr_icon = "mdi:form-textbox"
    _attr_native_min = 1
    _attr_native_max = 64
    _attr_mode = TextMode.TEXT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "virtual_preset_name")

    @property
    def native_value(self) -> str:
        return self.coordinator.virtual_preset_name

    async def async_set_value(self, value: str) -> None:
        self.coordinator.set_virtual_preset_name(value)
