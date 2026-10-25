"""A client for the Matter Server WebSocket API, the one python-matter-server and its matter.js successor share.

The server sends a server info object (`fabric_id`, `schema_version`, `sdk_version` and so on) as
soon as the socket opens. Requests are `{"message_id", "command", "args"}`. Answers are
`{"message_id", "result"}` or `{"message_id", "error_code", "details"}`. After `start_listening`
the server returns every node with its attributes, keyed by `endpoint/cluster/attribute` paths of
decimal ids, and then pushes events as `{"event", "data"}`, such as `attribute_updated` with
`[node_id, path, value]` and `node_updated` with the whole node.

Error codes from the server. 0 unknown, 1 commission failed, 2 interview failed, 3 node not ready,
4 node not resolving, 5 node doesn't exist, 6 version mismatch, 7 SDK stack error, 8 invalid
arguments, 9 invalid command.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import json
import time
from typing import Any, Final

from openhal.drivers.base import DriverError

ERRORS: Final = {
    0: "unknown error",
    1: "commissioning failed",
    2: "interview failed",
    3: "node not ready",
    4: "node not resolving",
    5: "node doesn't exist",
    6: "version mismatch",
    7: "SDK stack error",
    8: "invalid arguments",
    9: "invalid command",
}
MIN_SCHEMA: Final = 5


class MatterClient:
    """One WebSocket session with a Matter Server, following one node."""

    def __init__(self, url: str, node: int, *, timeout: float) -> None:
        self.url = url
        self.node = node
        self.timeout = timeout
        self.server: dict[str, Any] = {}
        self.attributes: dict[str, Any] = {}
        self.stamps: dict[str, float] = {}
        self.available = False
        self.info: dict[str, Any] = {}
        self._ws: Any = None
        self._task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[Any]] = {}
        self._ids = itertools.count(1)
        self._lost = ""

    @property
    def where(self) -> str:
        return f"Matter node {self.node} on {self.url}"

    async def open(self) -> None:
        from websockets.asyncio.client import connect

        try:
            ws = await connect(self.url, open_timeout=self.timeout, proxy=None, max_size=32 * 2**20)
        except (OSError, TimeoutError) as exc:
            raise DriverError(
                f"Could not open the Matter Server at {self.url} ({exc}). Check the URL and port 5580."
            ) from None
        except Exception as exc:  # noqa: BLE001
            raise DriverError(f"The Matter Server at {self.url} refused the WebSocket ({exc}).") from None
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), self.timeout))
        except Exception as exc:  # noqa: BLE001
            await ws.close()
            raise DriverError(f"The Matter Server at {self.url} sent no server info ({exc}).") from None
        if not isinstance(hello, dict) or "schema_version" not in hello:
            await ws.close()
            raise DriverError(f"{self.url} isn't a Matter Server. It didn't start with its server info.")
        if int(hello.get("schema_version") or 0) < MIN_SCHEMA:
            await ws.close()
            raise DriverError(
                f"The Matter Server speaks schema {hello.get('schema_version')}. Update it to {MIN_SCHEMA} or newer."
            )
        self.server = hello
        self._ws = ws
        self._lost = ""
        self._task = asyncio.create_task(self._reader(ws))
        nodes = await self.call("start_listening")
        node = next((item for item in nodes or [] if isinstance(item, dict) and item.get("node_id") == self.node), None)
        if node is None:
            await self.close()
            raise DriverError(f"The Matter Server has no node {self.node}. Check node against the server's node list.")
        self._load(node)

    def _load(self, node: dict[str, Any]) -> None:
        now = time.time()
        self.info = {key: value for key, value in node.items() if key != "attributes"}
        self.available = bool(node.get("available"))
        self.attributes = dict(node.get("attributes") or {})
        self.stamps = dict.fromkeys(self.attributes, now)

    async def _reader(self, ws: Any) -> None:
        try:
            async for raw in ws:
                self._message(raw)
            self._lost = "the Matter Server closed the WebSocket"
        except Exception as exc:  # noqa: BLE001
            self._lost = f"the WebSocket failed ({exc})"
        for future in self._pending.values():
            if not future.done():
                future.set_exception(DriverError(f"{self.where} disconnected ({self._lost}). Reconnect it."))
                future.exception()
        self._pending.clear()

    def _message(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except ValueError:
            return
        if not isinstance(message, dict):
            return
        if "message_id" in message:
            future = self._pending.pop(str(message["message_id"]), None)
            if future is None or future.done():
                return
            if "error_code" in message:
                code = message.get("error_code")
                reason = ERRORS.get(code, f"error {code}") if isinstance(code, int) else str(code)
                details = message.get("details")
                future.set_exception(
                    DriverError(f"The Matter Server refused the command ({reason}{f', {details}' if details else ''}).")
                )
                future.exception()
            else:
                future.set_result(message.get("result"))
            return
        event, data = message.get("event"), message.get("data")
        if event == "attribute_updated" and isinstance(data, list) and len(data) == 3 and data[0] == self.node:
            self.attributes[str(data[1])] = data[2]
            self.stamps[str(data[1])] = time.time()
        elif event in ("node_updated", "node_added") and isinstance(data, dict) and data.get("node_id") == self.node:
            self._load(data)
        elif event == "node_removed" and data == self.node:
            self.available = False
            self._lost = "the node was removed from the fabric"
        elif event == "server_shutdown":
            self._lost = "the Matter Server shut down"

    async def call(self, command: str, **args: Any) -> Any:
        if self._ws is None or self._lost:
            raise DriverError(f"{self.where} is not connected{f', {self._lost}' if self._lost else ''}. Reconnect it.")
        ident = str(next(self._ids))
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[ident] = future
        message: dict[str, Any] = {"message_id": ident, "command": command}
        if args:
            message["args"] = args
        try:
            await self._ws.send(json.dumps(message))
            return await asyncio.wait_for(future, self.timeout)
        except TimeoutError:
            raise TimeoutError(f"The Matter Server didn't answer {command} within {self.timeout:g} s.") from None
        except DriverError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._lost = f"sending failed ({exc})"
            raise DriverError(f"{self.where} disconnected while sending {command} ({exc}).") from None
        finally:
            self._pending.pop(ident, None)

    async def close(self) -> None:
        ws, task = self._ws, self._task
        self._ws = None
        self._task = None
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._lost

    @property
    def lost(self) -> str:
        """Why the session ended, or empty while it is up."""
        return self._lost or ("" if self._ws is not None else "not connected")
