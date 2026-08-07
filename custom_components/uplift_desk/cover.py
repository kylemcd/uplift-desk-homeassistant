"""Cover-style daily controls for an UPLIFT desk."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the desk cover entity."""
    async_add_entities([UpliftDeskCover(entry.runtime_data)])


class UpliftDeskCover(UpliftDeskEntity, CoverEntity):
    """Map sitting, standing, stop, and target position to a cover entity."""

    _attr_name = None
    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cover")

    @property
    def available(self) -> bool:
        """Require a command transport, validated limits, and mapped presets."""
        state = self.state_data
        presets = state.get("presets") or {}
        sit = state.get("sitPreset", 1)
        stand = state.get("standPreset", 2)
        return bool(
            super().available
            and self.command_transport_available
            and not state.get("monitorOnly", False)
            and state.get("minimumMm") is not None
            and state.get("maximumMm") is not None
            and presets.get(str(sit)) is not None
            and presets.get(str(stand)) is not None
        )

    @property
    def current_cover_position(self) -> int | None:
        position = self.state_data.get("coverPosition")
        return int(position) if position is not None else None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return position == 0 if position is not None else None

    @property
    def is_opening(self) -> bool:
        return self.state_data.get("moving") == "up"

    @property
    def is_closing(self) -> bool:
        return self.state_data.get("moving") == "down"

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self.coordinator.async_execute(self.coordinator.api.async_stand)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self.coordinator.async_execute(self.coordinator.api.async_sit)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self.coordinator.async_execute(self.coordinator.api.async_stop)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = int(kwargs[ATTR_POSITION])
        await self.coordinator.async_execute(
            lambda: self.coordinator.api.async_set_position(position)
        )
