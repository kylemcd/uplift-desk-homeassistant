"""Config flow for UPLIFT Desk."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from uplift_ble import DeskValidator

from .api import BluetoothBrokerApi, DeskApiError
from .const import (
    CONF_BROKER_URL,
    CONF_CONNECTION_TYPE,
    CONF_DESK_ID,
    CONNECTION_BLUETOOTH,
    CONNECTION_BROKER,
    DOMAIN,
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
