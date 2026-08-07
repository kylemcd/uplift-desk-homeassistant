"""Virtual-preset selection for an UPLIFT desk."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the virtual-preset selector."""
    async_add_entities([UpliftVirtualPresetSelect(entry.runtime_data)])


class UpliftVirtualPresetSelect(UpliftDeskEntity, SelectEntity):
    """Select one of the presets stored by Home Assistant."""

    _attr_name = "Virtual preset"
    _attr_icon = "mdi:desk"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "virtual_preset")

    @property
    def options(self) -> list[str]:
        return sorted(self.coordinator.virtual_presets, key=str.casefold)

    @property
    def current_option(self) -> str | None:
        return self.coordinator.selected_virtual_preset

    async def async_select_option(self, option: str) -> None:
        self.coordinator.select_virtual_preset(option)
