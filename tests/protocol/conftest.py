"""A real embedded hub with mock devices, served on a free loopback port, and clients for both transports.

The websocket client opens the hub's `/rpc` socket. The stdio client runs the same bridge
`openhal rpc` runs, fed through in-memory lines, so every test covers both transports. One test in
test_stdio.py also runs the real `openhal rpc` process.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from websockets.asyncio.client import ClientConnection, connect

from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.protocol.stdio import bridge
from openhal.spec import load, loads
from tests.kernel.conftest import FakeClock

FAN = """
device: Desk fan
id: desk-fan
connect: { mock: fan, initial: { fan_speed: 20 } }
read:
  temperature: { unit: degC, every: 1 s }
write:
  fan_speed: { unit: "%", min: 0, max: 100, step: 1, max_change_per_s: 20 }
actions:
  spin_test:
    args:
      seconds: { unit: s, min: 1, max: 30 }
    confirm: confirm
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: sohan, at: 2026-10-24 }
"""

HEATER = """
device: Curing heater
id: heater
connect: { mock: heater }
read:
  temp: { unit: degC, every: 1 s }
write:
  power: { unit: W, min: 0, max: 60 }
  mode: { type: enum, values: [off, eco, full] }
  enabled: { type: bool }
actions:
  pulse:
    args:
      seconds: { unit: s, min: 1, max: 10 }
    require: ["enabled == true"]
  purge: { confirm: confirm-each-time, effects: [power] }
safe_state: { power: 0 }
interlocks:
  - if: "power > 0 W"
    require: "desk-fan.fan_speed >= 30 %"
    message: "The heater needs the fan at 30 % or more."
watchdog:
  max_duration:
    - when: "power > 40 W"
      for: 60 s
hazard: medium
confirmed: { by: sohan, at: 2026-10-24 }
"""

DRAFT = """
device: Draft lamp
id: draft-lamp
connect: { mock: lamp }
write:
  brightness: { unit: percent, min: 0, max: 100 }
"""

VERSION = "2026-10-24"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def hub(tmp_path: Path, clock: FakeClock) -> AsyncIterator[Hub]:
    hub = Hub(HubConfig(home=tmp_path), clock=clock, in_memory=True)
    path = tmp_path / "desk-fan.hal.yaml"
    path.write_text(FAN, encoding="utf-8")
    hub.add_device(load(path), path=path)
    hub.add_device(loads(HEATER))
    hub.add_device(loads(DRAFT))
    await hub.start(load_devices=False)
    clock.advance(60)
    yield hub
    await hub.close()


@pytest.fixture
async def base_url(hub: Hub) -> AsyncIterator[str]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(hub), log_level="warning", lifespan="off"))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    while not server.started:  # noqa: ASYNC110
        await asyncio.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    await task
    listener.close()


@pytest.fixture
def tokens(hub: Hub) -> dict[str, str]:
    return {
        "human": hub.tokens.create("sohan", "human")[0],
        "agent": hub.tokens.create("claude", "agent", "control_medium")[0],
        "reader": hub.tokens.create("viewer", "agent", "read")[0],
        "other": hub.tokens.create("other", "agent", "control_medium")[0],
    }


class Rpc:
    """A protocol client. It sends text, collects notifications and matches responses by id."""

    def __init__(self, send: Callable[[str], Awaitable[None]], frames: asyncio.Queue[str]) -> None:
        self._send = send
        self._frames = frames
        self._next = 0
        self.responses: dict[Any, dict[str, Any]] = {}
        self.notes: list[dict[str, Any]] = []
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)
        await self._send(text)

    async def _pull(self, wait_s: float) -> None:
        text = await asyncio.wait_for(self._frames.get(), wait_s)
        message = json.loads(text)
        if isinstance(message, dict) and "method" in message and "id" not in message:
            self.notes.append(message)
        else:
            self.responses[message.get("id") if isinstance(message, dict) else None] = message

    async def response(self, request_id: Any, wait_s: float = 10.0) -> dict[str, Any]:
        while request_id not in self.responses:
            await self._pull(wait_s)
        return self.responses.pop(request_id)

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next += 1
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": self._next, "method": method}
        if params is not None:
            message["params"] = params
        await self.send_text(json.dumps(message))
        return await self.response(self._next)

    async def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """The result of a request that must succeed."""
        response = await self.request(method, params)
        assert "result" in response, response
        result: dict[str, Any] = response["result"]
        return result

    async def error(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """The error of a request that must fail."""
        response = await self.request(method, params)
        assert "error" in response, response
        error: dict[str, Any] = response["error"]
        return error

    async def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        await self.send_text(json.dumps(message))

    async def initialize(self, token: str | None = None, *, version: str = VERSION) -> dict[str, Any]:
        params: dict[str, Any] = {"protocolVersion": version, "clientInfo": {"name": "pytest", "version": "1.0"}}
        if token is not None:
            params["token"] = token
        result = await self.call("hal/initialize", params)
        await self.notify("hal/initialized")
        return result

    async def note(self, method: str, wait_s: float = 5.0, **match: Any) -> dict[str, Any]:
        """Wait for a notification whose params contain `match`."""
        deadline = asyncio.get_running_loop().time() + wait_s
        seen = 0
        while True:
            for message in self.notes[seen:]:
                params = message.get("params", {})
                if message["method"] == method and all(params.get(key) == value for key, value in match.items()):
                    return message
            seen = len(self.notes)
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise AssertionError(f"no {method} notification matching {match}, got {self.notes}")
            with contextlib.suppress(TimeoutError):
                await self._pull(remaining)


@contextlib.asynccontextmanager
async def websocket_client(base_url: str, header_token: str | None) -> AsyncIterator[Rpc]:
    url = base_url.replace("http://", "ws://") + "/rpc"
    headers = {"Authorization": f"Bearer {header_token}"} if header_token else {}
    async with connect(url, additional_headers=headers) as connection:
        frames: asyncio.Queue[str] = asyncio.Queue()
        reader = asyncio.create_task(_read_socket(connection, frames))
        try:
            yield Rpc(connection.send, frames)
        finally:
            reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await reader


async def _read_socket(connection: ClientConnection, frames: asyncio.Queue[str]) -> None:
    async for frame in connection:
        frames.put_nowait(frame if isinstance(frame, str) else frame.decode())


@contextlib.asynccontextmanager
async def stdio_client(base_url: str, header_token: str | None) -> AsyncIterator[Rpc]:
    url = base_url.replace("http://", "ws://") + "/rpc"
    lines: asyncio.Queue[bytes] = asyncio.Queue()
    frames: asyncio.Queue[str] = asyncio.Queue()

    async def send(text: str) -> None:
        lines.put_nowait(text.encode() + b"\n")

    task = asyncio.create_task(bridge(url, header_token, lines.get, frames.put_nowait))
    try:
        yield Rpc(send, frames)
    finally:
        lines.put_nowait(b"")
        with contextlib.suppress(TimeoutError, Exception):
            await asyncio.wait_for(task, 5)
        task.cancel()


Connect = Callable[..., contextlib.AbstractAsyncContextManager[Rpc]]


@pytest.fixture(params=["websocket", "stdio"])
def transport(request: pytest.FixtureRequest, base_url: str) -> Connect:
    """Open a client on the transport under test. `header` sends the token as an Authorization header."""
    opener = websocket_client if request.param == "websocket" else stdio_client

    def open_client(header: str | None = None) -> contextlib.AbstractAsyncContextManager[Rpc]:
        return opener(base_url, header)

    return open_client
