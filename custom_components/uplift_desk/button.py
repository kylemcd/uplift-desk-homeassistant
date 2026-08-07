"""Safe daily command buttons for an UPLIFT desk."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from hashlib import sha256

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
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
    ),
    UpliftButtonDescription(
        key="jog_down",
        name="Jog down",
        icon="mdi:arrow-down",
        action="jog_down",
    ),
    UpliftButtonDescription(
        key="recall_virtual_preset",
        name="Recall virtual preset",
        icon="mdi:desk",
        action="recall_virtual_preset",
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
    registry = er.async_get(hass)
    address = str(entry.runtime_data.data.get("address", "unknown"))
    virtual_preset_buttons = [
        UpliftVirtualPresetButton(entry.runtime_data, name)
        for name in sorted(entry.runtime_data.virtual_presets, key=str.casefold)
    ]
    virtual_preset_unique_ids = {
        _unique_id(address, _virtual_preset_key(button.preset_name))
        for button in virtual_preset_buttons
    }
    virtual_preset_prefix = _unique_id(address, "virtual_preset_go_")
    jog_unique_ids = {
        _unique_id(address, key)
        for key in ("jog_up", "jog_down")
    }
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registry_entry.unique_id.startswith(virtual_preset_prefix)
            and registry_entry.unique_id not in virtual_preset_unique_ids
        ):
            registry.async_remove(registry_entry.entity_id)
            continue
        if (
            registry_entry.unique_id in jog_unique_ids
            and registry_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        ):
            registry.async_update_entity(registry_entry.entity_id, disabled_by=None)
    async_add_entities(
        [
            *(
                UpliftDeskButton(entry.runtime_data, description)
                for description in BUTTONS
            ),
            *virtual_preset_buttons,
        ]
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
        if action == "recall_virtual_preset":
            selected = self.coordinator.selected_virtual_preset
            if selected is None or selected not in self.coordinator.virtual_presets:
                return False
            height = self.coordinator.virtual_presets[selected]
            minimum = state.get("minimumMm")
            maximum = state.get("maximumMm")
            return bool(
                minimum is not None
                and maximum is not None
                and minimum <= height <= maximum
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
            "recall_virtual_preset": self.coordinator.async_recall_virtual_preset,
            "release": api.async_release,
        }
        action = self.entity_description.action
        if action == "recall_virtual_preset":
            await actions[action]()
            return
        await self.coordinator.async_execute(actions[action])


class UpliftVirtualPresetButton(UpliftDeskEntity, ButtonEntity):
    """Move directly to one Home Assistant virtual preset."""

    _attr_icon = "mdi:desk"

    def __init__(self, coordinator, preset_name: str) -> None:
        super().__init__(coordinator, _virtual_preset_key(preset_name))
        self.preset_name = preset_name
        self._attr_name = f"Go to {preset_name}"

    @property
    def available(self) -> bool:
        state = self.state_data
        height = self.coordinator.virtual_presets.get(self.preset_name)
        minimum = state.get("minimumMm")
        maximum = state.get("maximumMm")
        return bool(
            super().available
            and state.get("connected")
            and not state.get("monitorOnly", False)
            and height is not None
            and minimum is not None
            and maximum is not None
            and minimum <= height <= maximum
        )

    async def async_press(self) -> None:
        await self.coordinator.async_recall_virtual_preset_named(self.preset_name)


def _virtual_preset_key(name: str) -> str:
    digest = sha256(name.casefold().encode()).hexdigest()[:12]
    return f"virtual_preset_go_{digest}"


def _unique_id(address: str, key: str) -> str:
    return f"{address}_{key}".lower().replace(":", "")
