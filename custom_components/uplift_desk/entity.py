"""Shared UPLIFT Desk entity model."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import UpliftDeskCoordinator


class UpliftDeskEntity(CoordinatorEntity[UpliftDeskCoordinator]):
    """Base entity backed by a desk transport."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: UpliftDeskCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.address}_{key}".lower().replace(":", "")

    @property
    def state_data(self) -> dict[str, Any]:
        """Return the latest desk state."""
        return self.coordinator.data

    @property
    def address(self) -> str:
        """Return the desk Bluetooth address."""
        return str(self.coordinator.data.get("address", "unknown"))

    @property
    def command_transport_available(self) -> bool:
        """Return whether commands can be sent now or via broker reconnect."""
        return bool(
            self.state_data.get("connected") or self.coordinator.api.mode == "broker"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the desk as one Home Assistant device."""
        profile = self.state_data.get("profile") or {}
        device_info = DeviceInfo(
            identifiers={(DOMAIN, self.address)},
            connections={(dr.CONNECTION_BLUETOOTH, self.address)},
            name=str(self.state_data.get("name", "UPLIFT Desk")),
            manufacturer="UPLIFT Desk",
            model="Bluetooth Adapter",
            hw_version=str(profile.get("variant", "Jiecang BLE")),
        )
        if self.coordinator.api.configuration_url:
            device_info["configuration_url"] = self.coordinator.api.configuration_url
        return device_info
