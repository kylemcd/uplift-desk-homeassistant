"""Sensors for an UPLIFT desk."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .const import MM_PER_INCH
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up desk sensors."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            UpliftHeightSensor(coordinator),
            UpliftMovementSensor(coordinator),
            UpliftErrorSensor(coordinator),
        ]
    )


class UpliftHeightSensor(UpliftDeskEntity, SensorEntity):
    _attr_name = "Height"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.INCHES
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "height")

    @property
    def native_value(self) -> float | None:
        value = self.state_data.get("heightMm")
        return round(float(value) / MM_PER_INCH, 2) if value is not None else None


class UpliftMovementSensor(UpliftDeskEntity, SensorEntity):
    _attr_name = "Movement"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = ["stopped", "up", "down"]

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "movement")

    @property
    def native_value(self) -> str:
        return str(self.state_data.get("moving", "stopped"))


class UpliftErrorSensor(UpliftDeskEntity, SensorEntity):
    _attr_name = "Error"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "error")

    @property
    def native_value(self) -> str:
        return str(self.state_data.get("error") or "none")
