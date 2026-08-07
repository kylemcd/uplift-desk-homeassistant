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
        if self.entity_description.action == "release":
            return super().available
        return bool(
            super().available
            and self.state_data.get("connected")
            and not self.state_data.get("monitorOnly", False)
        )

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
