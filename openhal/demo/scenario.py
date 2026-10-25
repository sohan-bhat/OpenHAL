"""Run the plant waterer scenario against a real hub and record what the hub answered.

`run()` starts a hub on a loopback port with the plant waterer mock
(examples/plant-waterer/mock/plant-waterer.hal.yaml), connects as an agent over the `/rpc`
WebSocket and sends three commands. A 120 s watering is over the limit. A 20 s watering waits on an
empty tank. After a refill, a 20 s watering runs and the soil gets wetter. `openhal demo --record`
writes the result to docs/demo/scenario.yaml, and the README, the docs and the website take every
number from that file.

Times are left out of the record, so two runs give the same file. The simulated board runs `speed`
times faster than real time, so the demo takes a few seconds instead of half a minute.
"""

from __future__ import annotations

import asyncio
import contextlib
import copy
import datetime as dt
import json
import socket
import tempfile
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Final

import uvicorn
import yaml
from websockets.asyncio.client import ClientConnection, connect

from openhal import __version__
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, PlantWatererSimulator
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.hub.views import quantity
from openhal.protocol.convert import window
from openhal.protocol.version import LATEST
from openhal.spec import load

DEVICE: Final = "plant-waterer"
FILE_NAME: Final = "plant-waterer.hal.yaml"
SPEED: Final = 40.0
WAIT_S: Final = 15.0
SCENARIO_PATH: Final = Path("docs") / "demo" / "scenario.yaml"


def example_file() -> Path:
    """The mock device file, from a checkout or from the installed package."""
    package = Path(__file__).resolve().parents[1]
    for root in (package, package.parent):
        candidate = root / "examples" / "plant-waterer" / "mock" / FILE_NAME
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"examples/plant-waterer/mock/{FILE_NAME} is missing from this install.")


def water(seconds: float) -> dict[str, Any]:
    return {"device": DEVICE, "action": "water", "args": {"duration": {"value": seconds, "unit": "s"}}}


class Agent:
    """A protocol client that keeps every frame, so the record shows exactly what the hub sent."""

    def __init__(self, socket_: ClientConnection) -> None:
        self.socket = socket_
        self.frames: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.notifications: list[dict[str, Any]] = []
        self._ids = 0
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        with contextlib.suppress(Exception):
            async for frame in self.socket:
                await self.frames.put(json.loads(frame))

    async def send(self, message: dict[str, Any]) -> None:
        await self.socket.send(json.dumps(message))

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one request and return the whole response, `result` or `error`."""
        self._ids += 1
        await self.send({"jsonrpc": "2.0", "id": self._ids, "method": method, "params": params})
        while True:
            message = await asyncio.wait_for(self.frames.get(), WAIT_S)
            if message.get("id") == self._ids:
                return message
            self.notifications.append(message)

    async def value(self, channel: str, wanted: Any = None, *, since: float = 0.0) -> Any:
        """Wait for the next `hal/value` of `channel` read after `since`, or for one that equals `wanted`."""
        while True:
            message = await asyncio.wait_for(self.frames.get(), WAIT_S)
            if "id" in message:
                continue
            self.notifications.append(message)
            params = message.get("params") or {}
            if message.get("method") != "hal/value" or params.get("device") != DEVICE:
                continue
            fresh = dt.datetime.fromisoformat(str(params.get("at"))).timestamp() >= since
            if params.get("channel") == channel and fresh and (wanted is None or params.get("value") == wanted):
                return params.get("value")

    async def close(self) -> None:
        self._reader.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._reader


@contextlib.asynccontextmanager
async def served(hub: Hub) -> AsyncIterator[str]:
    """The hub's API on a free loopback port, for as long as the block runs."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(hub), log_level="warning", lifespan="off", timeout_graceful_shutdown=2)
    )
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        while not server.started:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        yield f"ws://127.0.0.1:{port}/rpc"
    finally:
        server.should_exit = True
        await task
        listener.close()


def _exchange(name: str, before: str | None, request: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": name}
    if before:
        entry["before"] = before
    entry["request"] = copy.deepcopy({"method": request["method"], "params": request["params"]})
    if "error" in answer:
        entry["error"] = answer["error"]
    else:
        entry["result"] = answer.get("result")
    return entry


async def run(*, speed: float = SPEED) -> dict[str, Any]:
    """Run the scenario once and return the record."""
    path = example_file()
    file = load(path)
    board = PlantWatererSimulator(tank_ok=False, speed=speed)
    previous = SIMULATORS.get(DEVICE)
    SIMULATORS[DEVICE] = board
    with tempfile.TemporaryDirectory(prefix="openhal-demo-") as home:
        hub = Hub(HubConfig(home=Path(home)), in_memory=True)
        try:
            hub.add_device(file, path=path)
            await hub.start(load_devices=False)
            token, _ = hub.tokens.create("claude", "agent", "control_low")
            async with served(hub) as url, connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
                agent = Agent(ws)
                try:
                    client = {"name": "openhal-demo", "version": __version__}
                    await agent.call("hal/initialize", {"protocolVersion": LATEST, "clientInfo": client})
                    await agent.send({"jsonrpc": "2.0", "method": "hal/initialized"})
                    exchanges = await _exchanges(agent, board)
                finally:
                    await agent.close()
        finally:
            await hub.close()
            if previous is None:
                SIMULATORS.pop(DEVICE, None)
            else:
                SIMULATORS[DEVICE] = previous
    action = file.actions["water"]
    duration = action.args["duration"]
    assert duration.min is not None
    assert duration.max is not None
    assert duration.unit is not None
    confirmed = file.confirmed
    runs = action.max_runs
    return {
        "scenario": "plant-waterer",
        "recorded_with": "uv run openhal demo --record docs/demo/scenario.yaml",
        "protocol_version": LATEST,
        "device": DEVICE,
        "file": FILE_NAME,
        "confirmed": {"by": confirmed.by, "at": str(confirmed.at)} if confirmed else None,
        "limits": {
            "water_duration": {
                "min": quantity(duration.min, duration.unit),
                "max": quantity(duration.max, duration.unit),
            },
            "water_runs": {"count": runs.count, "per": window(runs.per)} if runs else None,
        },
        "exchanges": exchanges,
    }


async def _exchanges(agent: Agent, board: PlantWatererSimulator) -> list[dict[str, Any]]:
    await agent.value("tank", "empty")
    too_long: dict[str, Any] = {"method": "hal/action", "params": water(120)}
    first = await agent.call(too_long["method"], too_long["params"])
    empty: dict[str, Any] = {"method": "hal/action", "params": water(20)}
    second = await agent.call(empty["method"], empty["params"])
    board.refill()
    await agent.value("tank", "ok")
    before = await agent.value("soil_moisture")
    third = await agent.call(empty["method"], empty["params"])
    await asyncio.sleep(board.remaining_s())
    after = await agent.value("soil_moisture", since=time.time())
    watered = _exchange("watered", "tank refilled", empty, third)
    unit = "%"
    watered["soil_moisture"] = {"before": quantity(before, unit), "after": quantity(after, unit)}
    return [
        _exchange("too-long", None, too_long, first),
        _exchange("tank-empty", "tank is empty", empty, second),
        watered,
    ]


def dump(record: dict[str, Any]) -> str:
    """The record as YAML, in a stable order."""
    return yaml.safe_dump(record, sort_keys=False, allow_unicode=True, width=200)


def read(path: Path | None = None) -> dict[str, Any]:
    """The recorded scenario, from docs/demo/scenario.yaml by default."""
    target = path or Path(__file__).resolve().parents[2] / SCENARIO_PATH
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return data
