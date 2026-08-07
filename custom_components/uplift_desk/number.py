"""Target height staging for an UPLIFT desk."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up target height."""
    async_add_entities([UpliftTargetHeight(entry.runtime_data)])


class UpliftTargetHeight(UpliftDeskEntity, NumberEntity):
    _attr_name = "Target height"
    _attr_device_class = NumberDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.MILLIMETERS
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "target_height")

    @property
    def available(self) -> bool:
        return bool(
            super().available
            and self.state_data.get("connected")
            and not self.state_data.get("monitorOnly", False)
            and self.state_data.get("minimumMm") is not None
            and self.state_data.get("maximumMm") is not None
        )

    @property
    def native_min_value(self) -> float:
        return float(self.state_data.get("minimumMm", 0))

    @property
    def native_max_value(self) -> float:
        return float(self.state_data.get("maximumMm", 2000))

    @property
    def native_value(self) -> float | None:
        value = self.state_data.get("targetHeightMm")
        return float(value) if value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_execute(
            lambda: self.coordinator.api.async_set_target_height(value)
        )
