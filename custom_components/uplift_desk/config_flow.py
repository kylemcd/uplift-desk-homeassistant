"""Config flow for UPLIFT Desk."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME, UnitOfLength
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from uplift_ble import DeskValidator

from .api import BluetoothBrokerApi, DeskApiError
from .const import (
    CONF_BROKER_URL,
    CONF_CONNECTION_TYPE,
    CONF_DESK_ID,
    CONF_VIRTUAL_PRESETS,
    CONNECTION_BLUETOOTH,
    CONNECTION_BROKER,
    DOMAIN,
    MM_PER_INCH,
    SUPPORTED_SERVICE_UUIDS,
)

_LOGGER = logging.getLogger(__name__)


class UpliftDeskConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a native-Bluetooth or broker-backed UPLIFT desk."""

    VERSION = 2

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._broker_url: str | None = None
        self._broker_desks: dict[str, dict[str, Any]] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        _config_entry: ConfigEntry,
    ) -> UpliftDeskOptionsFlow:
        """Create the virtual-preset management flow."""
        return UpliftDeskOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how Home Assistant reaches the desk."""
        if user_input is not None:
            if user_input[CONF_CONNECTION_TYPE] == CONNECTION_BLUETOOTH:
                return await self.async_step_bluetooth_device()
            return await self.async_step_broker()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONNECTION_TYPE, default=CONNECTION_BLUETOOTH
                    ): vol.In(
                        {
                            CONNECTION_BLUETOOTH: "Home Assistant Bluetooth",
                            CONNECTION_BROKER: "Bluetooth Broker",
                        }
                    )
                }
            ),
        )

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle automatic Home Assistant Bluetooth discovery."""
        if not discovery_info.connectable:
            return self.async_abort(reason="not_connectable")
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        self.context["title_placeholders"] = {
            "name": self._display_name(discovery_info)
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm and validate a discovered Bluetooth desk."""
        if self._discovery_info is None:
            return self.async_abort(reason="no_devices_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            discovered = await self._validate_bluetooth(self._discovery_info)
            if discovered is None:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=discovered.name or self._display_name(self._discovery_info),
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_BLUETOOTH,
                        CONF_ADDRESS: discovered.address,
                        CONF_NAME: discovered.name or "UPLIFT Desk",
                    },
                )
        return self.async_show_form(step_id="bluetooth_confirm", errors=errors)

    async def async_step_bluetooth_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a desk from Home Assistant's Bluetooth discovery cache."""
        errors: dict[str, str] = {}
        self._collect_bluetooth_devices()
        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            info = self._discovered_devices[address]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            discovered = await self._validate_bluetooth(info)
            if discovered is None:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=discovered.name or self._display_name(info),
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_BLUETOOTH,
                        CONF_ADDRESS: discovered.address,
                        CONF_NAME: discovered.name or "UPLIFT Desk",
                    },
                )

        return self.async_show_form(
            step_id="bluetooth_device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: self._display_name(info)
                            for address, info in self._discovered_devices.items()
                        }
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_broker(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Connect to an optional network Bluetooth Broker."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._broker_url = user_input[CONF_BROKER_URL].rstrip("/")
            try:
                api = BluetoothBrokerApi(
                    async_get_clientsession(self.hass), self._broker_url, ""
                )
                await api.async_health()
                desks = await api.async_desks()
            except DeskApiError:
                errors["base"] = "cannot_connect"
            else:
                self._broker_desks = {
                    str(desk["id"]): desk for desk in desks if desk.get("id")
                }
                if not self._broker_desks:
                    errors["base"] = "no_broker_desks"
                elif len(self._broker_desks) == 1:
                    return await self._create_broker_entry(
                        next(iter(self._broker_desks))
                    )
                else:
                    return await self.async_step_broker_desk()

        return self.async_show_form(
            step_id="broker",
            data_schema=vol.Schema({vol.Required(CONF_BROKER_URL): str}),
            errors=errors,
        )

    async def async_step_broker_desk(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one desk exposed by a multi-desk broker."""
        if self._broker_url is None or not self._broker_desks:
            return self.async_abort(reason="no_broker_desks")
        if user_input is not None:
            return await self._create_broker_entry(user_input[CONF_DESK_ID])
        return self.async_show_form(
            step_id="broker_desk",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DESK_ID): vol.In(
                        {
                            desk_id: str(desk.get("name", desk_id))
                            for desk_id, desk in self._broker_desks.items()
                        }
                    )
                }
            ),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update broker connection details."""
        entry = self._get_reconfigure_entry()
        if entry.data.get(CONF_CONNECTION_TYPE) != CONNECTION_BROKER:
            return self.async_abort(reason="reconfigure_not_supported")
        errors: dict[str, str] = {}
        if user_input is not None:
            broker_url = user_input[CONF_BROKER_URL].rstrip("/")
            desk_id = user_input[CONF_DESK_ID]
            try:
                api = BluetoothBrokerApi(
                    async_get_clientsession(self.hass), broker_url, desk_id
                )
                await api.async_health()
                await api.async_state()
            except DeskApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_BROKER_URL: broker_url,
                        CONF_DESK_ID: desk_id,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BROKER_URL,
                        default=entry.data.get(CONF_BROKER_URL, ""),
                    ): str,
                    vol.Required(
                        CONF_DESK_ID, default=entry.data.get(CONF_DESK_ID, "")
                    ): str,
                }
            ),
            errors=errors,
        )

    async def _create_broker_entry(self, desk_id: str) -> ConfigFlowResult:
        assert self._broker_url is not None
        desk = self._broker_desks[desk_id]
        address = str(desk.get("address", desk_id))
        await self.async_set_unique_id(address, raise_on_progress=False)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=str(desk.get("name", "UPLIFT Desk")),
            data={
                CONF_CONNECTION_TYPE: CONNECTION_BROKER,
                CONF_BROKER_URL: self._broker_url,
                CONF_DESK_ID: desk_id,
            },
        )

    async def _validate_bluetooth(self, info: BluetoothServiceInfoBleak):
        validator = DeskValidator(
            client_factory=lambda device, timeout: BleakClient(device, timeout=timeout)
        )
        try:
            return await validator.validate_device(info.device, timeout=10)
        except Exception:
            _LOGGER.exception("Unexpected error validating Bluetooth desk")
            return None

    def _collect_bluetooth_devices(self) -> None:
        current_ids = self._async_current_ids(include_ignore=False)
        for info in bluetooth.async_discovered_service_info(
            self.hass, connectable=True
        ):
            if (
                info.address in current_ids
                or info.address in self._discovered_devices
                or not self._matches_supported_service(info)
            ):
                continue
            self._discovered_devices[info.address] = info

    @staticmethod
    def _matches_supported_service(info: BluetoothServiceInfoBleak) -> bool:
        return bool(set(info.service_uuids) & SUPPORTED_SERVICE_UUIDS)

    @staticmethod
    def _display_name(info: BluetoothServiceInfoBleak) -> str:
        return f"{info.name or 'UPLIFT Desk'} ({info.address})"


class UpliftDeskOptionsFlow(OptionsFlowWithReload):
    """Manage Home Assistant virtual presets with ordinary forms."""

    def __init__(self) -> None:
        self._presets: dict[str, float] | None = None
        self._editing_name: str | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the virtual-preset management menu."""
        self._load_presets()
        menu_options = ["add_preset"]
        if self._presets:
            menu_options.extend(("edit_preset", "delete_preset"))
        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={"presets": self._preset_summary()},
        )

    async def async_step_add_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a named virtual preset."""
        self._load_presets()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = self._normalize_name(user_input["preset_name"])
            if not name:
                errors["preset_name"] = "invalid_name"
            elif self._matching_name(name) is not None:
                errors["preset_name"] = "already_exists"
            else:
                self._presets[name] = self._inches_to_mm(
                    user_input["preset_height"]
                )
                return self._save()
        return self.async_show_form(
            step_id="add_preset",
            data_schema=self._preset_schema(
                default_name="",
                default_height=self._current_height_inches(),
            ),
            errors=errors,
        )

    async def async_step_edit_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a virtual preset to edit."""
        self._load_presets()
        if not self._presets:
            return await self.async_step_add_preset()
        if user_input is not None:
            self._editing_name = user_input["preset"]
            return await self.async_step_edit_preset_form()
        return self.async_show_form(
            step_id="edit_preset",
            data_schema=self._preset_selection_schema(),
        )

    async def async_step_edit_preset_form(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the selected virtual preset."""
        self._load_presets()
        if self._editing_name is None or self._editing_name not in self._presets:
            return await self.async_step_init()
        errors: dict[str, str] = {}
        if user_input is not None:
            name = self._normalize_name(user_input["preset_name"])
            existing_name = self._matching_name(name)
            if not name:
                errors["preset_name"] = "invalid_name"
            elif existing_name is not None and existing_name != self._editing_name:
                errors["preset_name"] = "already_exists"
            else:
                del self._presets[self._editing_name]
                self._presets[name] = self._inches_to_mm(
                    user_input["preset_height"]
                )
                return self._save()
        return self.async_show_form(
            step_id="edit_preset_form",
            data_schema=self._preset_schema(
                default_name=self._editing_name,
                default_height=self._presets[self._editing_name] / MM_PER_INCH,
            ),
            errors=errors,
        )

    async def async_step_delete_preset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete a selected virtual preset."""
        self._load_presets()
        if not self._presets:
            return await self.async_step_init()
        if user_input is not None:
            del self._presets[user_input["preset"]]
            return self._save()
        return self.async_show_form(
            step_id="delete_preset",
            data_schema=self._preset_selection_schema(),
        )

    def _load_presets(self) -> None:
        if self._presets is not None:
            return
        self._presets = {
            str(name): float(height)
            for name, height in self.config_entry.options.get(
                CONF_VIRTUAL_PRESETS, {}
            ).items()
        }

    def _preset_schema(
        self, *, default_name: str, default_height: float
    ) -> vol.Schema:
        minimum, maximum = self._height_bounds_inches()
        return vol.Schema(
            {
                vol.Required("preset_name", default=default_name): vol.All(
                    str, vol.Length(max=64)
                ),
                vol.Required(
                    "preset_height", default=round(default_height, 1)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=round(minimum, 1),
                        max=round(maximum, 1),
                        step=0.1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement=UnitOfLength.INCHES,
                    )
                ),
            }
        )

    def _preset_selection_schema(self) -> vol.Schema:
        assert self._presets is not None
        return vol.Schema(
            {
                vol.Required("preset"): vol.In(
                    {
                        name: f"{name} ({height / MM_PER_INCH:.1f} in)"
                        for name, height in sorted(self._presets.items())
                    }
                )
            }
        )

    def _height_bounds_inches(self) -> tuple[float, float]:
        coordinator = self.config_entry.runtime_data
        state = getattr(coordinator, "data", {}) or {}
        minimum = state.get("minimumMm")
        maximum = state.get("maximumMm")
        if minimum is None or maximum is None or maximum <= minimum:
            return 20.0, 60.0
        return float(minimum) / MM_PER_INCH, float(maximum) / MM_PER_INCH

    def _current_height_inches(self) -> float:
        coordinator = self.config_entry.runtime_data
        state = getattr(coordinator, "data", {}) or {}
        height = state.get("heightMm") or state.get("targetHeightMm")
        if height is not None:
            return float(height) / MM_PER_INCH
        minimum, _maximum = self._height_bounds_inches()
        return minimum

    def _preset_summary(self) -> str:
        assert self._presets is not None
        if not self._presets:
            return "No virtual presets configured."
        return "\n".join(
            f"• {name}: {height / MM_PER_INCH:.1f} in"
            for name, height in sorted(self._presets.items())
        )

    def _save(self) -> ConfigFlowResult:
        assert self._presets is not None
        options = dict(self.config_entry.options)
        options[CONF_VIRTUAL_PRESETS] = dict(self._presets)
        return self.async_create_entry(title="", data=options)

    @staticmethod
    def _normalize_name(value: str) -> str:
        return " ".join(value.split())

    def _matching_name(self, name: str) -> str | None:
        assert self._presets is not None
        name_casefold = name.casefold()
        return next(
            (
                existing
                for existing in self._presets
                if existing.casefold() == name_casefold
            ),
            None,
        )

    @staticmethod
    def _inches_to_mm(value: float) -> float:
        return round(float(value) * MM_PER_INCH, 1)
