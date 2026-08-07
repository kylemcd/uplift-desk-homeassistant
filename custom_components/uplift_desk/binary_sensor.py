"""Binary sensors for an UPLIFT desk."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up desk binary sensors."""
    coordinator = entry.runtime_data
    entities = [
        UpliftConnectedSensor(coordinator),
        UpliftResetRequiredSensor(coordinator),
    ]
    entities.extend(
        UpliftPresenceSensor(
            coordinator,
            str(target["id"]),
            str(target.get("name") or "Device near desk"),
        )
        for target in coordinator.data.get("presenceTargets", [])
        if isinstance(target, dict) and target.get("id")
    )
    async_add_entities(entities)


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


class UpliftPresenceSensor(UpliftDeskEntity, BinarySensorEntity):
    """Report a private-BLE target resolved and measured by the broker."""

    _attr_device_class = BinarySensorDeviceClass.PRESENCE

    def __init__(self, coordinator, target_id: str, name: str) -> None:
        super().__init__(coordinator, f"presence_{target_id}")
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
    def is_on(self) -> bool:
        return bool(self._target and self._target.get("near"))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        target = self._target or {}
        return {
            "rssi": target.get("rssi"),
            "last_seen_at": target.get("lastSeenAt"),
        }

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
