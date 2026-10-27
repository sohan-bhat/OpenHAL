"""Run the print babysitter scenario against a real hub and record what the hub answered.

Someone starts a long print and asks an agent to keep an eye on it. `run()` starts a hub on a
loopback port with two simulated devices from examples/print-babysitter/, a Klipper printer behind
the Moonraker simulator and the printer's webcam (openhal/demo/webcam.py). It connects as an agent
over the `/rpc` WebSocket and sends six requests.

1. It reads a camera frame. A corner of the first layer is lifting.
2. It raises `bed_target` from 60 degC to 70 degC, inside the limit, so it is done.
3. It asks for a 300 degC nozzle and gets LIMIT_EXCEEDED, since the limit is 260 degC.
4. Later it reads another frame. The print has come loose.
5. It pauses the print, which is done straight away.
6. It asks to cancel. Cancelling can't be undone, so the hub answers pending until a person decides.

`openhal demo --record` writes the result to docs/demo/scenario.yaml, and the README, the docs and
the website take every number from that file. Times, image pixels and the hub's random request id
are left out, so two runs give the same file.
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
from openhal.demo.webcam import SimulatedWebcam, Webcam
from openhal.drivers.moonraker.driver import MoonrakerDriver
from openhal.drivers.moonraker.simulator import MoonrakerSim
from openhal.hub.api import create_app
from openhal.hub.config import HubConfig
from openhal.hub.hub import Hub
from openhal.protocol.version import LATEST
from openhal.spec import load
from openhal.spec.models import DeviceFile

FOLDER: Final = "print-babysitter"
DEVICE: Final = "printer"
CAMERA: Final = "printer-cam"
FILES: Final = {DEVICE: "printer.hal.yaml", CAMERA: "printer-cam.hal.yaml"}
FRAMES: Final = ("first-layer", "come-loose")
BED_PRINTING: Final = 60.0
NOZZLE_PRINTING: Final = 215.0
BED_WARMER: Final = 70
NOZZLE_ASKED: Final = 300
SETTLE_S: Final = 1.0
"""How long the agent waits between reading bed_target and raising it, so the rate limit is met."""
WAIT_S: Final = 15.0
REQUEST_ID: Final = "REQUEST_ID"
"""What the record shows in place of the hub's request id, which is random on every run."""
SCENARIO_PATH: Final = Path("docs") / "demo" / "scenario.yaml"
RECORDED_WITH: Final = "uv run openhal demo --record docs/demo/scenario.yaml"


def example(folder: str, *parts: str) -> Path:
    """A file under examples/<folder>/, from a checkout or from the installed package."""
    package = Path(__file__).resolve().parents[1]
    for root in (package, package.parent):
        candidate = root.joinpath("examples", folder, *parts)
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"examples/{folder}/{'/'.join(parts)} is missing from this install.")


def frame(name: str) -> bytes:
    """One of the demo's camera frames, a line drawing in examples/print-babysitter/frames/."""
    return example(FOLDER, "frames", f"{name}.jpg").read_bytes()


class SimulatedPrinter(MoonrakerDriver):
    """The Moonraker driver on the Moonraker simulator. It reports itself as simulated."""

    def __init__(self, device: DeviceFile, sim: MoonrakerSim) -> None:
        super().__init__(device, http_transport=sim.http_transport())

    @property
    def simulated(self) -> bool:
        return True


class PrinterSim(MoonrakerSim):
    """The Moonraker simulator on a host named printer, as examples/print-babysitter/printer.hal.yaml expects."""

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        result = await super().call(method, params)
        if method == "printer.info" and isinstance(result, dict):
            return {**result, "hostname": "printer"}
        return result


def printing() -> MoonrakerSim:
    """A simulated Klipper printer a few minutes into a long print, heaters at their targets."""
    sim = PrinterSim()
    objects = sim.state.objects
    objects["print_stats"].update({"state": "printing", "filename": "enclosure-lid.gcode", "print_duration": 312.0})
    objects["virtual_sdcard"].update({"progress": 0.04, "is_active": True})
    objects["heater_bed"].update({"temperature": BED_PRINTING, "target": BED_PRINTING})
    objects["extruder"].update({"temperature": NOZZLE_PRINTING, "target": NOZZLE_PRINTING})
    objects["toolhead"]["homed_axes"] = "xyz"
    return sim


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

    async def value(self, device: str, channel: str, wanted: Any = None, *, since: float = 0.0) -> Any:
        """Wait for the next `hal/value` of a channel read after `since`, or for one that equals `wanted`."""
        while True:
            message = await asyncio.wait_for(self.frames.get(), WAIT_S)
            if "id" in message:
                continue
            self.notifications.append(message)
            params = message.get("params") or {}
            if message.get("method") != "hal/value" or params.get("device") != device:
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


def _exchange(name: str, request: dict[str, Any], answer: dict[str, Any], **extra: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": name, **{key: value for key, value in extra.items() if value is not None}}
    entry["request"] = copy.deepcopy(request)
    if "error" in answer:
        entry["error"] = answer["error"]
    else:
        entry["result"] = _without_time(answer.get("result"))
    return entry


def _without_time(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    shown = {key: value for key, value in result.items() if key != "at"}
    image = shown.get("value")
    if isinstance(image, dict) and "data" in image:
        shown["value"] = {key: value for key, value in image.items() if key != "data"}
    return shown


async def run() -> dict[str, Any]:
    """Run the scenario once and return the record, with the hub's real request id."""
    files = {device: example(FOLDER, name) for device, name in FILES.items()}
    printer, camera = load(files[DEVICE]), load(files[CAMERA])
    sim = printing()
    webcam = Webcam({name: frame(name) for name in FRAMES}, FRAMES[0])
    with tempfile.TemporaryDirectory(prefix="openhal-demo-") as home:
        hub = Hub(HubConfig(home=Path(home)), in_memory=True)
        try:
            hub.add_device(printer, driver=SimulatedPrinter(printer, sim), path=files[DEVICE])
            hub.add_device(camera, driver=SimulatedWebcam(camera, webcam), path=files[CAMERA])
            await hub.start(load_devices=False)
            token, _ = hub.tokens.create("claude", "agent", "control_medium")
            async with served(hub) as url, connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
                agent = Agent(ws)
                try:
                    client = {"name": "openhal-demo", "version": __version__}
                    await agent.call("hal/initialize", {"protocolVersion": LATEST, "clientInfo": client})
                    await agent.send({"jsonrpc": "2.0", "method": "hal/initialized"})
                    devices = [await _described(agent, device) for device in FILES]
                    exchanges = await _exchanges(agent, webcam)
                finally:
                    await agent.close()
        finally:
            await hub.close()
    return {
        "scenario": FOLDER,
        "recorded_with": RECORDED_WITH,
        "protocol_version": LATEST,
        "devices": devices,
        "exchanges": exchanges,
    }


async def _described(agent: Agent, device: str) -> dict[str, Any]:
    """What the hub says about a device, its file, confirmation and limits."""
    answer = await agent.call("hal/devices/describe", {"device": device})
    view = answer["result"]["device"]
    limits = {
        name: {
            "min": {"value": channel["min"], "unit": channel["unit"]},
            "max": {"value": channel["max"], "unit": channel["unit"]},
            "max_change_per_s": {"value": channel["maxChangePerS"], "unit": f"{channel['unit']}/s"},
        }
        for name, channel in view["write"].items()
    }
    return {
        "id": view["id"],
        "name": view["name"],
        "driver": view["driver"],
        "hazard": view["hazard"],
        "file": view["file"],
        "confirmed": view["confirmed"],
        "read": list(view["read"]),
        "limits": limits,
        "actions": {name: {"confirm": action["confirm"]} for name, action in view["actions"].items()},
    }


def _target(channel: str, value: int) -> dict[str, Any]:
    return {"method": "hal/write", "params": {"device": DEVICE, "channel": channel, "value": value, "unit": "degC"}}


async def _exchanges(agent: Agent, webcam: Webcam) -> list[dict[str, Any]]:
    look: dict[str, Any] = {"method": "hal/read", "params": {"device": CAMERA, "channel": "frame"}}
    await agent.value(DEVICE, "state", "printing")
    bed = await agent.call("hal/read", {"device": DEVICE, "channel": "bed_target"})
    read_at = time.monotonic()
    first = await agent.call(look["method"], look["params"])
    await asyncio.sleep(max(0.0, read_at + SETTLE_S - time.monotonic()))
    warmer = _target("bed_target", BED_WARMER)
    raised = await agent.call(warmer["method"], warmer["params"])
    hotter = _target("extruder_target", NOZZLE_ASKED)
    refused = await agent.call(hotter["method"], hotter["params"])
    webcam.show(FRAMES[1])
    second = await agent.call(look["method"], look["params"])
    pause: dict[str, Any] = {"method": "hal/action", "params": {"device": DEVICE, "action": "pause"}}
    paused = await agent.call(pause["method"], pause["params"])
    cancel: dict[str, Any] = {"method": "hal/action", "params": {"device": DEVICE, "action": "cancel"}}
    waiting = await agent.call(cancel["method"], cancel["params"])
    before = {key: bed["result"][key] for key in ("value", "unit")}
    after = {key: raised["result"][key] for key in ("value", "unit")} if "result" in raised else None
    return [
        _exchange("first-layer", look, first, before="the agent checks the first layer", frame=_frame(FRAMES[0])),
        _exchange(
            "bed-warmer",
            warmer,
            raised,
            before="a corner of the first layer is lifting",
            bed_target={"before": before, "after": after},
        ),
        _exchange("nozzle-too-hot", hotter, refused),
        _exchange("come-loose", look, second, before="later", frame=_frame(FRAMES[1])),
        _exchange("paused", pause, paused, before="the print has come loose"),
        _exchange("cancel-waits", cancel, waiting, before="cancelling can't be undone"),
    ]


def _frame(name: str) -> str:
    return f"examples/{FOLDER}/frames/{name}.jpg"


def recorded(record: dict[str, Any]) -> dict[str, Any]:
    """The record as the file keeps it, with REQUEST_ID in place of the hub's random request id."""
    kept = copy.deepcopy(record)
    for entry in kept["exchanges"]:
        result = entry.get("result")
        if isinstance(result, dict) and "requestId" in result:
            result["requestId"] = REQUEST_ID
            entry["masked"] = ["requestId"]
    return kept


def dump(record: dict[str, Any]) -> str:
    """The record as YAML, in a stable order."""
    return yaml.safe_dump(recorded(record), sort_keys=False, allow_unicode=True, width=200)


def read(path: Path | None = None) -> dict[str, Any]:
    """The recorded scenario, from docs/demo/scenario.yaml by default."""
    target = path or Path(__file__).resolve().parents[2] / SCENARIO_PATH
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return data


def exchange(record: dict[str, Any], name: str) -> dict[str, Any]:
    """One exchange of a record by its id, such as `nozzle-too-hot`."""
    found: dict[str, Any] = next(entry for entry in record["exchanges"] if entry["id"] == name)
    return found
