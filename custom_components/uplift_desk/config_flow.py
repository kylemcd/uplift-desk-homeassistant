"""Config flow for UPLIFT Desk."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BluetoothBrokerApi, BrokerApiError
from .const import CONF_BROKER_URL, DEFAULT_BROKER_URL, DOMAIN


class UpliftDeskConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a Bluetooth Broker-backed UPLIFT desk."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle initial setup."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                state = await self._validate(user_input[CONF_BROKER_URL])
            except BrokerApiError:
                errors["base"] = "cannot_connect"
            else:
                address = str(state["address"])
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=str(state.get("name", "UPLIFT Desk")),
                    data={CONF_BROKER_URL: user_input[CONF_BROKER_URL].rstrip("/")},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BROKER_URL,
                        default=(user_input or {}).get(
                            CONF_BROKER_URL, DEFAULT_BROKER_URL
                        ),
                    ): str
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the broker URL."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._validate(user_input[CONF_BROKER_URL])
            except BrokerApiError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_BROKER_URL: user_input[CONF_BROKER_URL].rstrip("/")
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BROKER_URL,
                        default=(user_input or {}).get(
                            CONF_BROKER_URL, entry.data[CONF_BROKER_URL]
                        ),
                    ): str
                }
            ),
            errors=errors,
        )

    async def _validate(self, broker_url: str) -> dict[str, Any]:
        api = BluetoothBrokerApi(async_get_clientsession(self.hass), broker_url)
        await api.async_health()
        return await api.async_state()
