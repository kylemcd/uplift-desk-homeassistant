"""Native Home Assistant Bluetooth transport for UPLIFT desks."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import establish_connection
from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from uplift_ble import DeskController, DeskEventType, DiscoveredDesk
from uplift_ble.desk_configs import DESK_CONFIGS_BY_SERVICE

from .api import DeskCommandError, DeskConnectionError

_LOGGER = logging.getLogger(__name__)


class BluetoothDeskApi:
    """Control one desk through Home Assistant's managed Bluetooth adapters."""

    mode = "bluetooth"
    configuration_url: str | None = None

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        self._hass = hass
        self.address = address.upper()
        self.name = name
        self._client: BleakClient | None = None
        self._controller: DeskController | None = None
        self._connect_lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._released_until: datetime | None = None
        self._target_height_mm: float | None = None
        self._state: dict[str, Any] = {
            "id": self.address.lower().replace(":", ""),
            "address": self.address,
            "name": self.name,
            "connected": False,
            "monitorOnly": False,
            "moving": "stopped",
            "error": None,
            "resetRequired": False,
            "presets": {},
            "sitPreset": 1,
            "standPreset": 2,
            "connectionMode": self.mode,
        }

    async def async_state(self) -> dict[str, Any]:
        if not self._is_released:
            await self._async_ensure_connected()
        return dict(self._state)

    async def async_sit(self) -> None:
        controller = await self._async_controller()
        self._require_known_preset(1)
        self._set_movement_toward(self._preset_height(1))
        await self._async_run_command(controller.move_to_height_preset_1)

    async def async_stand(self) -> None:
        controller = await self._async_controller()
        self._require_known_preset(2)
        self._set_movement_toward(self._preset_height(2))
        await self._async_run_command(controller.move_to_height_preset_2)

    async def async_stop(self) -> None:
        controller = await self._async_controller()
        await self._async_run_command(controller.stop_movement)
        self._state["moving"] = "stopped"

    async def async_set_position(self, position: int) -> None:
        minimum, maximum = self._effective_limits()
        bounded = max(0, min(100, position))
        target = minimum + ((maximum - minimum) * bounded / 100)
        await self._async_move_to_height(target)

    async def async_set_target_height(self, height_mm: float) -> None:
        minimum, maximum = self._effective_limits()
        if not minimum <= height_mm <= maximum:
            raise DeskCommandError("Target height is outside the known desk limits")
        self._target_height_mm = height_mm
        self._state["targetHeightMm"] = height_mm

    async def async_move_to_target(self) -> None:
        if self._target_height_mm is None:
            raise DeskCommandError("No target height has been staged")
        await self._async_move_to_height(self._target_height_mm)

    async def async_jog(self, direction: str) -> None:
        if direction not in {"up", "down"}:
            raise DeskCommandError("Jog direction must be up or down")
        controller = await self._async_controller()
        move = controller.move_up if direction == "up" else controller.move_down
        async with self._command_lock:
            self._state["moving"] = direction
            try:
                await move()
                await asyncio.sleep(0.5)
            finally:
                await controller.stop_movement()
                self._state["moving"] = "stopped"

    async def async_release(self) -> None:
        self._released_until = datetime.now(UTC) + timedelta(minutes=10)
        await self.async_close()
        self._state["releasedUntil"] = self._released_until.isoformat()

    async def async_close(self) -> None:
        controller, client = self._controller, self._client
        self._controller = None
        self._client = None
        self._state["connected"] = False
        if controller is not None:
            try:
                await controller.stop()
            except (BleakError, EOFError) as error:
                _LOGGER.debug("Error stopping desk notifications: %s", error)
        if client is not None and client.is_connected:
            await client.disconnect()

    @property
    def _is_released(self) -> bool:
        if self._released_until is None:
            return False
        if datetime.now(UTC) < self._released_until:
            return True
        self._released_until = None
        self._state.pop("releasedUntil", None)
        return False

    async def _async_controller(self) -> DeskController:
        if self._is_released:
            raise DeskConnectionError("Desk is temporarily released for another client")
        await self._async_ensure_connected()
        if self._controller is None:
            raise DeskConnectionError("Desk is not connected")
        return self._controller

    async def _async_ensure_connected(self) -> None:
        if self._client is not None and self._client.is_connected:
            return
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return
            ble_device = bluetooth.async_ble_device_from_address(
                self._hass, self.address, connectable=True
            )
            if ble_device is None:
                raise DeskConnectionError(
                    f"Bluetooth device {self.address} is not currently reachable"
                )
            try:
                client = await establish_connection(
                    BleakClient,
                    ble_device,
                    self.name,
                    disconnected_callback=self._handle_disconnect,
                    max_attempts=3,
                )
            except Exception as error:
                raise DeskConnectionError(str(error)) from error

            config = next(
                (
                    DESK_CONFIGS_BY_SERVICE[service.uuid]
                    for service in client.services
                    if service.uuid in DESK_CONFIGS_BY_SERVICE
                ),
                None,
            )
            if config is None:
                await client.disconnect()
                raise DeskConnectionError(
                    "Device does not expose a supported desk profile"
                )

            discovered = DiscoveredDesk(self.address, self.name, config)
            controller = discovered.create_controller(client, notification_timeout=0.2)
            self._register_events(controller)
            try:
                await controller.start()
                await controller.request_height_limits()
            except Exception as error:
                await client.disconnect()
                raise DeskConnectionError(str(error)) from error

            self._client = client
            self._controller = controller
            self._state.update(
                {
                    "connected": True,
                    "profile": {
                        "variant": config.desk_variant.value,
                        "serviceUuid": config.service_uuid,
                        "inputCharacteristicUuid": config.input_char_uuid,
                        "outputCharacteristicUuid": config.output_char_uuid,
                    },
                }
            )

    @callback
    def _handle_disconnect(self, _client: BleakClient) -> None:
        self._client = None
        self._controller = None
        self._state["connected"] = False
        self._state["moving"] = "stopped"

    def _register_events(self, controller: DeskController) -> None:
        controller.on(DeskEventType.HEIGHT, self._handle_height)
        controller.on(DeskEventType.HEIGHT_LIMITS_CONFIGURATION, self._handle_limits)
        controller.on(DeskEventType.HEIGHT_LIMIT_MAX, self._handle_maximum)
        controller.on(DeskEventType.HEIGHT_LIMIT_MIN, self._handle_minimum)
        controller.on(DeskEventType.ERROR_CODE, self._handle_error)
        controller.on(DeskEventType.RESET, self._handle_reset)
        for number, event in enumerate(
            (
                DeskEventType.HEIGHT_PRESET_1,
                DeskEventType.HEIGHT_PRESET_2,
                DeskEventType.HEIGHT_PRESET_3,
                DeskEventType.HEIGHT_PRESET_4,
            ),
            start=1,
        ):
            controller.on(
                event, lambda value, number=number: self._set_preset(number, value)
            )

    def _handle_height(self, height_mm: float) -> None:
        previous = self._state.get("heightMm")
        self._state["heightMm"] = height_mm
        minimum = self._state.get("minimumMm")
        maximum = self._state.get("maximumMm")
        if minimum is not None and maximum is not None and maximum > minimum:
            self._state["coverPosition"] = round(
                max(0, min(100, (height_mm - minimum) * 100 / (maximum - minimum)))
            )
        if previous is not None:
            delta = height_mm - float(previous)
            if abs(delta) < 0.2:
                self._state["moving"] = "stopped"
            else:
                self._state["moving"] = "up" if delta > 0 else "down"

    def _handle_limits(self, maximum: int, minimum: int) -> None:
        self._state["maximumMm"] = maximum
        self._state["minimumMm"] = minimum

    def _handle_maximum(self, maximum: int) -> None:
        self._state["maximumMm"] = maximum

    def _handle_minimum(self, minimum: int) -> None:
        self._state["minimumMm"] = minimum

    def _handle_error(self, error: Any) -> None:
        self._state["error"] = getattr(error, "value", str(error))

    def _handle_reset(self) -> None:
        self._state["resetRequired"] = True

    def _set_preset(self, number: int, value: int) -> None:
        presets = dict(self._state.get("presets") or {})
        presets[str(number)] = value
        self._state["presets"] = presets

    async def _async_run_command(self, command: Any) -> None:
        async with self._command_lock:
            try:
                await command()
            except Exception as error:
                raise DeskCommandError(str(error)) from error

    async def _async_move_to_height(self, height_mm: float) -> None:
        minimum, maximum = self._effective_limits()
        if not minimum <= height_mm <= maximum:
            raise DeskCommandError("Target height is outside the known desk limits")
        controller = await self._async_controller()
        self._set_movement_toward(height_mm)
        await self._async_run_command(
            lambda: controller.move_to_specified_height(round(height_mm))
        )

    def _effective_limits(self) -> tuple[float, float]:
        minimum = self._state.get("minimumMm")
        maximum = self._state.get("maximumMm")
        if minimum is None or maximum is None or maximum <= minimum:
            raise DeskCommandError("Desk height limits are not known")
        return float(minimum), float(maximum)

    def _preset_height(self, number: int) -> float:
        return float((self._state.get("presets") or {})[str(number)])

    def _require_known_preset(self, number: int) -> None:
        value = (self._state.get("presets") or {}).get(str(number))
        if value is None:
            raise DeskCommandError(f"Desk preset {number} is not known")
        minimum, maximum = self._effective_limits()
        if not minimum <= float(value) <= maximum:
            raise DeskCommandError(f"Desk preset {number} is outside known limits")

    def _set_movement_toward(self, target: float) -> None:
        current = self._state.get("heightMm")
        if current is None or abs(float(current) - target) < 0.2:
            self._state["moving"] = "stopped"
        else:
            self._state["moving"] = "up" if target > float(current) else "down"
