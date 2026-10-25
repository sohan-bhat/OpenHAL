"""A small asyncio client of the hub protocol over the `/rpc` WebSocket.

It initializes, sends requests one at a time and returns their results. Notifications that arrive
meanwhile are kept in `notifications`. A JSON-RPC error raises `ProtocolError` carrying the
registry name, number, reason and data.
"""

from __future__ import annotations

import itertools
import json
from types import TracebackType
from typing import Any, Final

from websockets.asyncio.client import ClientConnection, connect

from openhal import __version__
from openhal.protocol.stdio import rpc_url
from openhal.protocol.version import LATEST

OPEN_TIMEOUT_S: Final = 5.0


class ProtocolError(Exception):
    """A JSON-RPC error from the hub."""

    def __init__(self, error: dict[str, Any]) -> None:
        self.code: int = int(error.get("code", 0))
        self.reason: str = str(error.get("message", ""))
        self.data: dict[str, Any] = dict(error.get("data") or {})
        self.name: str = str(self.data.get("name", ""))
        super().__init__(f"{self.name} ({self.code}). {self.reason}")


class ProtocolClient:
    """`async with ProtocolClient(url, token) as hub: await hub.call("hal/devices/list")`."""

    def __init__(self, base_url: str, token: str | None, *, client_name: str = "openhal-client") -> None:
        self.url = rpc_url(base_url)
        self.token = token
        self.client_name = client_name
        self.initialize_result: dict[str, Any] = {}
        self.notifications: list[dict[str, Any]] = []
        self._socket: ClientConnection | None = None
        self._ids = itertools.count(1)

    async def __aenter__(self) -> ProtocolClient:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self._socket = await connect(self.url, additional_headers=headers, open_timeout=OPEN_TIMEOUT_S)
        params = {"protocolVersion": LATEST, "clientInfo": {"name": self.client_name, "version": __version__}}
        self.initialize_result = await self.call("hal/initialize", params)
        await self._send({"jsonrpc": "2.0", "method": "hal/initialized"})
        return self

    async def __aexit__(
        self, kind: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        if self._socket is None:
            return
        try:
            await self._send({"jsonrpc": "2.0", "method": "hal/shutdown"})
        finally:
            await self._socket.close()
            self._socket = None

    async def _send(self, message: dict[str, Any]) -> None:
        assert self._socket is not None, "use ProtocolClient as an async context manager"
        await self._socket.send(json.dumps(message))

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send one request and return its result, or raise ProtocolError."""
        request_id = next(self._ids)
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        assert self._socket is not None
        while True:
            frame = await self._socket.recv()
            message = json.loads(frame)
            if "method" in message and "id" not in message:
                self.notifications.append(message)
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise ProtocolError(message["error"])
            result: dict[str, Any] = message["result"]
            return result
