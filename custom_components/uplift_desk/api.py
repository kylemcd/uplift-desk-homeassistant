"""HTTP client for the private Bluetooth Broker."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from aiohttp import ClientError, ClientSession


class BrokerApiError(Exception):
    """Base error raised by the Bluetooth Broker client."""


class BrokerConnectionError(BrokerApiError):
    """The broker could not be reached."""


class BrokerCommandError(BrokerApiError):
    """The broker rejected a command."""


class BluetoothBrokerApi:
    """Small typed client for broker endpoints used by Home Assistant."""

    def __init__(self, session: ClientSession, base_url: str) -> None:
        self._session = session
        self.base_url = base_url.rstrip("/")

    async def async_health(self) -> dict[str, Any]:
        return await self._request("GET", "/healthz")

    async def async_state(self) -> dict[str, Any]:
        return await self._request("GET", "/api/desks/kyles-desk/state")

    async def async_sit(self) -> None:
        await self._request("POST", "/api/desks/kyles-desk/sit", json={})

    async def async_stand(self) -> None:
        await self._request("POST", "/api/desks/kyles-desk/stand", json={})

    async def async_stop(self) -> None:
        await self.async_command({"type": "stop"})

    async def async_set_position(self, position: int) -> None:
        await self._request(
            "POST",
            "/api/desks/kyles-desk/position",
            json={"position": position},
        )

    async def async_set_target_height(self, height_mm: float) -> None:
        await self._request(
            "PUT",
            "/api/desks/kyles-desk/target",
            json={"heightMm": round(height_mm)},
        )

    async def async_move_to_target(self) -> None:
        await self._request("POST", "/api/desks/kyles-desk/move-to-target", json={})

    async def async_jog(self, direction: str) -> None:
        await self._request(
            "POST",
            "/api/desks/kyles-desk/jog",
            json={"direction": direction, "durationMs": 500},
        )

    async def async_release(self) -> None:
        await self._request(
            "POST",
            "/api/desks/kyles-desk/release",
            json={"durationMs": 600_000},
        )

    async def async_command(self, command: dict[str, Any]) -> None:
        await self._request(
            "POST",
            "/api/desks/kyles-desk/commands",
            json={"requestId": str(uuid4()), "command": command},
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            async with asyncio.timeout(10):
                async with self._session.request(
                    method, f"{self.base_url}{path}", json=json
                ) as response:
                    payload = await response.json(content_type=None)
                    if response.status >= 400:
                        message = payload.get("error", response.reason)
                        raise BrokerCommandError(str(message))
                    return payload
        except BrokerCommandError:
            raise
        except (TimeoutError, ClientError) as error:
            raise BrokerConnectionError(str(error)) from error
