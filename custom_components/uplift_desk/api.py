"""Desk transport interfaces and Bluetooth Broker client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, Protocol
from urllib.parse import quote
from uuid import uuid4

from aiohttp import ClientError, ClientSession


class DeskApiError(Exception):
    """Base error raised by a desk transport."""


class DeskConnectionError(DeskApiError):
    """The desk transport could not be reached."""


class DeskCommandError(DeskApiError):
    """The desk transport rejected a command."""


class DeskApi(Protocol):
    """Common interface implemented by native Bluetooth and broker transports."""

    mode: str
    configuration_url: str | None

    async def async_state(self) -> dict[str, Any]: ...
    async def async_sit(self) -> None: ...
    async def async_stand(self) -> None: ...
    async def async_stop(self) -> None: ...
    async def async_set_position(self, position: int) -> None: ...
    async def async_set_target_height(self, height_mm: float) -> None: ...
    async def async_move_to_target(self) -> None: ...
    async def async_jog(self, direction: str) -> None: ...
    async def async_release(self) -> None: ...
    async def async_close(self) -> None: ...


class BluetoothBrokerApi:
    """HTTP client for an optional Bluetooth Broker transport."""

    mode = "broker"

    def __init__(self, session: ClientSession, base_url: str, desk_id: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")
        self.desk_id = desk_id
        self.configuration_url: str | None = self.base_url

    @property
    def _desk_path(self) -> str:
        return f"/api/desks/{quote(self.desk_id, safe='')}"

    async def async_health(self) -> dict[str, Any]:
        payload = await self._request("GET", "/healthz")
        if not isinstance(payload, dict):
            raise DeskConnectionError("Invalid broker health response")
        return payload

    async def async_desks(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/desks")
        if not isinstance(payload, list) or not all(
            isinstance(item, dict) for item in payload
        ):
            raise DeskConnectionError("Invalid broker desk inventory response")
        return payload

    async def async_state(self) -> dict[str, Any]:
        payload = await self._request("GET", f"{self._desk_path}/state")
        if not isinstance(payload, dict):
            raise DeskConnectionError("Invalid broker desk state response")
        return payload

    async def async_sit(self) -> None:
        await self._request("POST", f"{self._desk_path}/sit", json={})

    async def async_stand(self) -> None:
        await self._request("POST", f"{self._desk_path}/stand", json={})

    async def async_stop(self) -> None:
        await self.async_command({"type": "stop"})

    async def async_set_position(self, position: int) -> None:
        await self._request(
            "POST",
            f"{self._desk_path}/position",
            json={"position": position},
        )

    async def async_set_target_height(self, height_mm: float) -> None:
        await self._request(
            "PUT",
            f"{self._desk_path}/target",
            json={"heightMm": round(height_mm)},
        )

    async def async_move_to_target(self) -> None:
        await self._request("POST", f"{self._desk_path}/move-to-target", json={})

    async def async_jog(self, direction: str) -> None:
        await self._request(
            "POST",
            f"{self._desk_path}/jog",
            json={"direction": direction, "durationMs": 500},
        )

    async def async_release(self) -> None:
        await self._request(
            "POST",
            f"{self._desk_path}/release",
            json={"durationMs": 600_000},
        )

    async def async_command(self, command: dict[str, Any]) -> None:
        await self._request(
            "POST",
            f"{self._desk_path}/commands",
            json={"requestId": str(uuid4()), "command": command},
        )

    async def async_close(self) -> None:
        """Close transport resources. The shared HTTP session remains open."""

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        try:
            async with asyncio.timeout(10):
                async with self._session.request(
                    method, f"{self.base_url}{path}", json=json
                ) as response:
                    payload = await response.json(content_type=None)
                    if response.status >= 400:
                        message = (
                            payload.get("error", response.reason)
                            if isinstance(payload, dict)
                            else response.reason
                        )
                        raise DeskCommandError(str(message))
                    return payload
        except DeskCommandError:
            raise
        except (TimeoutError, ClientError, ValueError) as error:
            raise DeskConnectionError(str(error)) from error


DeskOperation = Awaitable[None]

# Compatibility aliases for integrations upgrading from 0.2.x.
BrokerApiError = DeskApiError
BrokerConnectionError = DeskConnectionError
BrokerCommandError = DeskCommandError
