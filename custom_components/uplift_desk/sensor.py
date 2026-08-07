"""Sensors for an UPLIFT desk."""

from __future__ import annotations

from typing import ClassVar

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfSignalStrength
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
    entities = [
        UpliftHeightSensor(coordinator),
        UpliftMovementSensor(coordinator),
        UpliftErrorSensor(coordinator),
    ]
    entities.extend(
        UpliftPresenceRssiSensor(
            coordinator,
            str(target["id"]),
            f"{str(target.get('name') or 'Device near desk')} signal",
        )
        for target in coordinator.data.get("presenceTargets", [])
        if isinstance(target, dict) and target.get("id")
    )
    async_add_entities(entities)


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


class UpliftPresenceRssiSensor(UpliftDeskEntity, SensorEntity):
    """Expose the latest broker-measured RSSI for a presence target."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = UnitOfSignalStrength.DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, target_id: str, name: str) -> None:
        super().__init__(coordinator, f"presence_{target_id}_rssi")
        self._target_id = target_id
        self._attr_name = name

    @property
    def available(self) -> bool:
        target = self._target
        return (
            super().available
            and target is not None
            and bool(target.get("tracking"))
        )

    @property
    def native_value(self) -> int | None:
        value = self._target.get("rssi") if self._target else None
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def _target(self) -> dict[str, object] | None:
        return next(
            (
                target
                for target in self.state_data.get("presenceTargets", [])
                if isinstance(target, dict) and target.get("id") == self._target_id
            ),
            None,
        )
