"""Safe daily command buttons for an UPLIFT desk."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import UpliftDeskConfigEntry
from .entity import UpliftDeskEntity


@dataclass(frozen=True, kw_only=True)
class UpliftButtonDescription(ButtonEntityDescription):
    """Describe a broker button operation."""

    action: str


BUTTONS = (
    UpliftButtonDescription(
        key="move_to_target",
        name="Move to target",
        icon="mdi:arrow-expand-vertical",
        action="move",
    ),
    UpliftButtonDescription(key="sit", name="Sit", icon="mdi:seat", action="sit"),
    UpliftButtonDescription(
        key="stand", name="Stand", icon="mdi:human-male", action="stand"
    ),
    UpliftButtonDescription(
        key="stop", name="Stop", icon="mdi:stop-circle", action="stop"
    ),
    UpliftButtonDescription(
        key="jog_up",
        name="Jog up",
        icon="mdi:arrow-up",
        action="jog_up",
        entity_registry_enabled_default=False,
    ),
    UpliftButtonDescription(
        key="jog_down",
        name="Jog down",
        icon="mdi:arrow-down",
        action="jog_down",
        entity_registry_enabled_default=False,
    ),
    UpliftButtonDescription(
        key="release",
        name="Release for phone",
        icon="mdi:bluetooth-off",
        action="release",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UpliftDeskConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up daily desk buttons."""
    async_add_entities(
        [UpliftDeskButton(entry.runtime_data, description) for description in BUTTONS]
    )


class UpliftDeskButton(UpliftDeskEntity, ButtonEntity):
    entity_description: UpliftButtonDescription

    def __init__(self, coordinator, description: UpliftButtonDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        state = self.state_data
        base_available = bool(
            super().available
            and state.get("connected")
            and not state.get("monitorOnly", False)
        )
        action = self.entity_description.action
        if action == "release":
            return bool(super().available and state.get("connected"))
        if not base_available:
            return False
        if action == "move":
            return bool(
                state.get("targetHeightMm") is not None
                and state.get("minimumMm") is not None
                and state.get("maximumMm") is not None
            )
        if action in {"sit", "stand"}:
            preset = (
                state.get("sitPreset", 1)
                if action == "sit"
                else state.get("standPreset", 2)
            )
            value = (state.get("presets") or {}).get(str(preset))
            minimum = state.get("minimumMm")
            maximum = state.get("maximumMm")
            return bool(
                value is not None
                and minimum is not None
                and maximum is not None
                and minimum <= value <= maximum
            )
        return True

    async def async_press(self) -> None:
        api = self.coordinator.api
        actions: dict[str, Callable[[], Awaitable[None]]] = {
            "move": api.async_move_to_target,
            "sit": api.async_sit,
            "stand": api.async_stand,
            "stop": api.async_stop,
            "jog_up": lambda: api.async_jog("up"),
            "jog_down": lambda: api.async_jog("down"),
            "release": api.async_release,
        }
        await self.coordinator.async_execute(actions[self.entity_description.action])
