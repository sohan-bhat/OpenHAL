"""Run the print babysitter scenario against a real hub and record what the hub answered.

Someone starts a long print and asks an agent to keep an eye on it. `run()` starts a hub on a
loopback port with two simulated devices from examples/print-babysitter/, a Klipper printer behind
the Moonraker simulator and the printer's webcam (openhal/demo/webcam.py). The agent and the owner
each connect over the `/rpc` WebSocket with a token of their own kind, and the story has seven
exchanges.

1. The agent reads a camera frame. A corner of the first layer is lifting.
2. The agent raises `bed_target` from 60 degC to 70 degC. The new target is inside the limit, so the
   write is done.
3. The agent asks for a 300 degC nozzle and gets LIMIT_EXCEEDED, since the limit is 260 degC.
4. Later the agent reads another frame. The print has come loose.
5. The agent pauses the print, which is done straight away.
6. The agent asks to cancel. Cancelling can't be undone, so the hub answers pending and sends the
   request to the owner.
7. The owner approves the cancel with the human token. The kernel checks the cancel again and grants
   the cancel, the driver sends the cancel to the printer, and Klipper reports the print cancelled.

Each exchange also keeps what the kernel did (the checks, the grant and the audit entries), the
commands the printer received, and the printer panel. The panel is the hub's view of the printer
(`GET /v1/devices/printer`), the view the Inspector shows. The view reports what the hub already
knows, so reading the panel sends nothing to the printer and adds nothing to the audit log. At the
end the owner reads the audit log with `hal/audit/query`, and the record keeps the story's entries
as `openhal log` prints them.

`openhal demo --record` writes the result to docs/demo/scenario.yaml, and the README, the docs and
the website take every number from that file. The simulated printer runs on a story clock that
moves only when the story moves it, and times, image pixels and the hub's random request id are
left out, so two runs give the same file.
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
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Final

import httpx
import uvicorn
import yaml
from websockets.asyncio.client import ClientConnection, connect

from openhal import __version__
from openhal.cli import log_cmd
from openhal.client.models import AuditEntry
from openhal.demo.webcam import SimulatedWebcam, Webcam
from openhal.drivers.moonraker.driver import MoonrakerDriver
from openhal.drivers.moonraker.simulator import KlipperState, MoonrakerSim
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
AGENT: Final = "claude"
AGENT_SCOPE: Final = "control_medium"
PERSON: Final = "owner"
BED_PRINTING: Final = 60.0
NOZZLE_PRINTING: Final = 215.0
BED_WARMER: Final = 70
NOZZLE_ASKED: Final = 300
PANEL: Final = ("state", "extruder_temp", "extruder_target", "bed_target")
"""The printer channels the panel shows. The landing story shows the bed target, so bed_temp is left out."""
COMMANDS: Final = frozenset(
    {
        "printer.gcode.script",
        "printer.print.pause",
        "printer.print.resume",
        "printer.print.cancel",
        "printer.emergency_stop",
    }
)
"""The Moonraker methods that tell the printer to do something. Queries and status calls are left out."""
CHECKS: Final = ("units", "range", "rate", "interlocks", "confirmation")
"""The kernel's checks of a write or an action, in the order the kernel runs them."""
READ_CHECKS: Final = ("channel", "device")
"""The kernel's checks of a read. A read needs no grant, and the kernel logs every read."""
ANSWERED_BY: Final = {
    "bad_unit": "units",
    "bad_value": "units",
    "bad_step": "units",
    "above_max": "range",
    "below_min": "range",
    "rate_limited": "rate",
    "interlock": "interlocks",
    "duration_exceeded": "interlocks",
    "needs_confirmation": "confirmation",
    "unknown_target": "channel",
    "device_unavailable": "device",
}
"""The check each kernel code comes from."""
SETTLE_S: Final = 1.0
"""How long the agent waits after the hub connects the printer before raising bed_target, so the rate limit is met."""
WAIT_S: Final = 15.0
REQUEST_ID: Final = "REQUEST_ID"
"""What the record shows in place of the hub's request id, which is random on every run."""
TIME: Final = "TIME"
"""What the record shows in place of each audit entry's time."""
SCENARIO_PATH: Final = Path("docs") / "demo" / "scenario.yaml"
RECORDED_WITH: Final = "uv run openhal demo --record docs/demo/scenario.yaml"
BEFORE: Final = {
    "first-layer": "the agent checks the first layer",
    "bed-warmer": "a corner of the first layer is lifting",
    "nozzle-too-hot": "a hotter nozzle might help the corner stick",
    "come-loose": "later the agent checks the print again",
    "paused": "the print has come loose",
    "cancel-waits": "cancelling can't be undone",
    "owner-approves": f"the {PERSON} approves the cancel",
}
"""The narration before each exchange, a `#` line in the trace."""


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
    """The Moonraker driver on the Moonraker simulator. The driver reports itself as simulated."""

    def __init__(self, device: DeviceFile, sim: MoonrakerSim) -> None:
        super().__init__(device, http_transport=sim.http_transport())

    @property
    def simulated(self) -> bool:
        return True


class StoryClock:
    """The simulated printer's clock. Time on the clock passes only when the story moves the clock on.

    The hub reads the printer on its own schedule, so a printer that followed the wall clock would
    report a different temperature on every run. On this clock every run reports the same one.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class PrinterSim(MoonrakerSim):
    """The Moonraker simulator on a host named printer, as printer.hal.yaml expects, on a story clock.

    `commands` keeps every command the printer received, G-code as its text and the print
    controls by their Moonraker method.
    """

    def __init__(self) -> None:
        self.clock = StoryClock()
        super().__init__(KlipperState(self.clock))
        self.commands: list[str] = []

    async def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if method in COMMANDS:
            script = (params or {}).get("script")
            self.commands.append(str(script) if method == "printer.gcode.script" else method)
        result = await super().call(method, params)
        if method == "printer.info" and isinstance(result, dict):
            return {**result, "hostname": "printer"}
        return result


def printing() -> PrinterSim:
    """A simulated Klipper printer a few minutes into a long print, heaters at their targets."""
    sim = PrinterSim()
    objects = sim.state.objects
    objects["print_stats"].update({"state": "printing", "filename": "enclosure-lid.gcode", "print_duration": 312.0})
    objects["virtual_sdcard"].update({"progress": 0.04, "is_active": True})
    objects["heater_bed"].update({"temperature": BED_PRINTING, "target": BED_PRINTING})
    objects["extruder"].update({"temperature": NOZZLE_PRINTING, "target": NOZZLE_PRINTING})
    objects["toolhead"]["homed_axes"] = "xyz"
    return sim


class Peer:
    """A protocol client that keeps every frame, so the record shows exactly what the hub sent.

    `label` is the principal the hub named in its `hal/initialize` answer, such as agent:claude.
    """

    def __init__(self, socket_: ClientConnection) -> None:
        self.socket = socket_
        self.frames: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.notifications: list[dict[str, Any]] = []
        self.label = ""
        self._ids = 0
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        with contextlib.suppress(Exception):
            async for frame in self.socket:
                await self.frames.put(json.loads(frame))

    async def send(self, message: dict[str, Any]) -> None:
        await self.socket.send(json.dumps(message))

    async def initialize(self) -> None:
        client = {"name": "openhal-demo", "version": __version__}
        answer = await self.call("hal/initialize", {"protocolVersion": LATEST, "clientInfo": client})
        principal = answer["result"]["principal"]
        self.label = f"{principal['kind']}:{principal['name']}"
        await self.send({"jsonrpc": "2.0", "method": "hal/initialized"})

    async def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one request and return the whole response, `result` or `error`."""
        self._ids += 1
        await self.send({"jsonrpc": "2.0", "id": self._ids, "method": method, "params": params})
        while True:
            message = await asyncio.wait_for(self.frames.get(), WAIT_S)
            if message.get("id") == self._ids:
                return message
            self.notifications.append(message)

    async def notified(self, method: str, wanted: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """The params of a notification that came, or comes next, with this method and params `wanted` accepts."""
        for message in self.notifications:
            if message.get("method") == method and wanted(message.get("params") or {}):
                return dict(message.get("params") or {})
        while True:
            message = await asyncio.wait_for(self.frames.get(), WAIT_S)
            if "id" in message:
                continue
            self.notifications.append(message)
            if message.get("method") == method and wanted(message.get("params") or {}):
                return dict(message.get("params") or {})

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


@contextlib.asynccontextmanager
async def joined(url: str, token: str) -> AsyncIterator[Peer]:
    """A session on the hub's `/rpc` socket with this token, initialized and ready for notifications."""
    async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as ws:
        peer = Peer(ws)
        try:
            await peer.initialize()
            yield peer
        finally:
            await peer.close()


class Panel:
    """The printer panel, read from the hub's view of the printer with the owner's token."""

    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def read(self) -> dict[str, Any]:
        answer = await self.http.get(f"/v1/devices/{DEVICE}")
        answer.raise_for_status()
        view = answer.json()
        channels = {**view["read"], **view["write"]}
        shown: dict[str, Any] = {}
        for name in PANEL:
            channel = channels[name]
            if not channel["known"]:
                raise RuntimeError(f"The hub doesn't know {DEVICE}.{name} yet, so the panel can't show it.")
            unit = channel.get("unit")
            shown[name] = channel["value"] if unit is None else {"value": channel["value"], "unit": unit}
        return shown


def _exchange(
    name: str,
    by: Peer,
    request: dict[str, Any],
    answer: dict[str, Any],
    printer: dict[str, Any],
    *,
    frame: str | None = None,
    bed_target: dict[str, Any] | None = None,
    printer_received: list[str] | None = None,
) -> dict[str, Any]:
    """One exchange in the record's order. `kernel` stays empty until the audit log is read."""
    entry: dict[str, Any] = {"id": name, "by": by.label, "before": BEFORE[name]}
    entry.update({key: value for key, value in (("frame", frame), ("bed_target", bed_target)) if value is not None})
    entry["request"] = copy.deepcopy(request)
    if "error" in answer:
        entry["error"] = answer["error"]
    else:
        entry["result"] = _without_time(answer.get("result"))
    entry["kernel"] = {}
    if printer_received is not None:
        entry["printer_received"] = printer_received
    entry["printer"] = printer
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
    """Run the scenario once and return the record, with the hub's real request id and audit times."""
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
            connected = time.monotonic()
            agent_token, _ = hub.tokens.create(AGENT, "agent", AGENT_SCOPE)
            person_token, _ = hub.tokens.create(PERSON, "human")
            async with (
                served(hub) as url,
                joined(url, agent_token) as agent,
                joined(url, person_token) as person,
                httpx.AsyncClient(
                    base_url="http" + url.removeprefix("ws").removesuffix("/rpc"),
                    headers={"Authorization": f"Bearer {person_token}"},
                ) as http,
            ):
                devices = [await _described(agent, device) for device in FILES]
                story = Story(agent, person, Panel(http), sim, webcam, connected)
                exchanges = await story.run()
                audit = await _audit(person, exchanges, story.requested_by)
        finally:
            await hub.close()
    return {
        "scenario": FOLDER,
        "recorded_with": RECORDED_WITH,
        "protocol_version": LATEST,
        "principals": {"agent": agent.label, "person": person.label},
        "devices": devices,
        "exchanges": exchanges,
        "audit": audit,
    }


async def _described(agent: Peer, device: str) -> dict[str, Any]:
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


def _action(name: str) -> dict[str, Any]:
    return {"method": "hal/action", "params": {"device": DEVICE, "action": name}}


class Story:
    """The seven exchanges, each with the commands the printer received and the panel afterwards."""

    def __init__(
        self, agent: Peer, person: Peer, panel: Panel, sim: PrinterSim, webcam: Webcam, connected: float
    ) -> None:
        self.agent = agent
        self.person = person
        self.panel = panel
        self.sim = sim
        self.webcam = webcam
        self.connected = connected
        self.requested_by = ""

    async def _send(self, peer: Peer, request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        mark = len(self.sim.commands)
        answer = await peer.call(request["method"], request["params"])
        return answer, self.sim.commands[mark:]

    async def run(self) -> list[dict[str, Any]]:
        agent, person, panel = self.agent, self.person, self.panel
        look: dict[str, Any] = {"method": "hal/read", "params": {"device": CAMERA, "channel": "frame"}}
        await agent.value(DEVICE, "state", "printing")
        first, _ = await self._send(agent, look)
        at_first = await panel.read()

        await asyncio.sleep(max(0.0, self.connected + SETTLE_S - time.monotonic()))
        warmer = _target("bed_target", BED_WARMER)
        raised, warmed = await self._send(agent, warmer)
        at_warm = await panel.read()
        after = {key: raised["result"][key] for key in ("value", "unit")} if "result" in raised else None

        hotter = _target("extruder_target", NOZZLE_ASKED)
        refused, not_sent = await self._send(agent, hotter)
        at_refused = await panel.read()

        self.webcam.show(FRAMES[1])
        second, _ = await self._send(agent, look)
        at_loose = await panel.read()

        pause = _action("pause")
        paused, pausing = await self._send(agent, pause)
        await agent.value(DEVICE, "state", "paused")
        at_pause = await panel.read()

        cancel = _action("cancel")
        waiting, held = await self._send(agent, cancel)
        at_wait = await panel.read()

        pending = (waiting.get("result") or {}).get("requestId")
        asked = await person.notified(
            "hal/confirmationRequested", lambda params: (params.get("request") or {}).get("requestId") == pending
        )
        self.requested_by = str(asked["request"]["requestedBy"])
        approve: dict[str, Any] = {"method": "hal/confirmations/approve", "params": {"requestId": pending}}
        approved, cancelling = await self._send(person, approve)
        await agent.value(DEVICE, "state", "cancelled")
        at_cancel = await panel.read()

        bed_target = {"before": at_first["bed_target"], "after": after}
        return [
            _exchange("first-layer", agent, look, first, at_first, frame=_frame(FRAMES[0])),
            _exchange("bed-warmer", agent, warmer, raised, at_warm, bed_target=bed_target, printer_received=warmed),
            _exchange("nozzle-too-hot", agent, hotter, refused, at_refused, printer_received=not_sent),
            _exchange("come-loose", agent, look, second, at_loose, frame=_frame(FRAMES[1])),
            _exchange("paused", agent, pause, paused, at_pause, printer_received=pausing),
            _exchange("cancel-waits", agent, cancel, waiting, at_wait, printer_received=held),
            _exchange("owner-approves", person, approve, approved, at_cancel, printer_received=cancelling),
        ]


def _frame(name: str) -> str:
    return f"examples/{FOLDER}/frames/{name}.jpg"


def _checks(names: tuple[str, ...], answered: str | None, word: str) -> dict[str, str]:
    """Each check in order, `ok` until the one that answered, which reads `word` and ends the list."""
    shown: dict[str, str] = {}
    for name in names:
        if name == answered:
            shown[name] = word
            break
        shown[name] = "ok"
    return shown


def _kernel(entry: dict[str, Any], logged: list[dict[str, Any]]) -> dict[str, Any]:
    """What the kernel did for one exchange, from the hub's answer and the audit entries the exchange made.

    A refusal from a check before these (a stop, read-only limits, the token's scope) lists no checks.
    """
    error = entry.get("error")
    result = entry.get("result") or {}
    code = str((error.get("data") or {}).get("kernelCode")) if error else ""
    read = entry["request"]["method"] == "hal/read"
    names = READ_CHECKS if read else CHECKS
    if error:
        checks = _checks(names, ANSWERED_BY[code], "blocked") if ANSWERED_BY.get(code) in names else {}
    elif result.get("status") == "pending":
        checks = _checks(names, "confirmation", "required")
    else:
        checks = _checks(names, None, "")
        if not read and entry["request"]["method"] != "hal/confirmations/approve":
            checks["confirmation"] = "not needed"
    kernel: dict[str, Any] = {"checks": checks}
    kernel["grant"] = "not needed" if read else ("issued" if result.get("status") == "done" else "none")
    approved_by = [item["body"]["approved_by"] for item in logged if (item.get("body") or {}).get("approved_by")]
    if approved_by:
        kernel["approved_by"] = approved_by[0]
    kernel["logged"] = [item["seq"] for item in logged]
    return kernel


def _expected(entry: dict[str, Any], requested_by: str) -> list[tuple[str, str, str, str]]:
    """The audit entries an exchange makes, as (event, principal, device, target)."""
    method, params = entry["request"]["method"], entry["request"]["params"]
    if method == "hal/confirmations/approve":
        target = (entry.get("result") or {}).get("target", "")
        device = (entry.get("result") or {}).get("device", "")
        return [("confirm", entry["by"], device, target), ("action", requested_by, device, target)]
    if method == "hal/read":
        return [("read", entry["by"], params["device"], f"read:{params['channel']}")]
    if method == "hal/write":
        return [("write", entry["by"], params["device"], f"write:{params['channel']}")]
    return [("action", entry["by"], params["device"], f"action:{params['action']}")]


def _entries_of(
    exchanges: list[dict[str, Any]], story: list[dict[str, Any]], requested_by: str
) -> list[list[dict[str, Any]]]:
    """The audit entries of each exchange, in order. `story` is the log from the first request, oldest first."""
    left = list(story)
    found: list[list[dict[str, Any]]] = []
    for entry in exchanges:
        mine = []
        for wanted in _expected(entry, requested_by):
            index = next(
                (
                    place
                    for place, item in enumerate(left)
                    if (item["event"], item["principal"], item.get("device"), item.get("target")) == wanted
                ),
                None,
            )
            if index is None:
                raise RuntimeError(f"The audit log has no {' '.join(wanted)} entry for the exchange {entry['id']}.")
            mine.append(left[index])
            del left[: index + 1]
        found.append(mine)
    return found


def _counts(story: list[dict[str, Any]]) -> dict[str, int]:
    """Requests an agent made, the ones the kernel refused, and the approvals a person gave.

    The run of an approved request carries `approved_by`. That run belongs to the request, so the
    count leaves the run out.
    """
    asked = [
        item
        for item in story
        if item["event"] in ("read", "write", "action")
        and item["principal"].startswith("agent:")
        and not (item.get("body") or {}).get("approved_by")
    ]
    return {
        "requests": len(asked),
        "refused": sum(item.get("status") == "blocked" for item in asked),
        "confirmed_by_a_person": sum(
            item["event"] == "confirm" and item.get("status") == "done" and item["principal"].startswith("human:")
            for item in story
        ),
    }


def _cells(item: dict[str, Any]) -> dict[str, str]:
    """One protocol AuditEntry as the columns `openhal log` prints."""
    entry = AuditEntry(
        seq=item["seq"],
        at=dt.datetime.fromisoformat(str(item["at"])).timestamp(),
        event=item["event"],
        principal=item["principal"],
        device=item.get("device"),
        target=item.get("target"),
        status=item.get("status"),
        code=item.get("code"),
        details=item.get("body") or {},
        hash=item["hash"],
    )
    return log_cmd.cells(entry)


async def _audit(person: Peer, exchanges: list[dict[str, Any]], requested_by: str) -> dict[str, Any]:
    """The owner reads the audit log. Every exchange gets its kernel facts, and the record gets the story's entries."""
    request: dict[str, Any] = {"method": "hal/audit/query", "params": {}}
    answer = await person.call(request["method"], request["params"])
    newest_first = answer["result"]["entries"]
    first_request = min(item["seq"] for item in newest_first if item["principal"] == exchanges[0]["by"])
    story = sorted((item for item in newest_first if item["seq"] >= first_request), key=lambda item: item["seq"])
    for entry, logged in zip(exchanges, _entries_of(exchanges, story, requested_by), strict=True):
        entry["kernel"] = _kernel(entry, logged)
    shown = [_cells(item) for item in reversed(story)]
    return {
        "request": request,
        "printed_with": f"uv run openhal log -n {len(shown)}",
        "counts": _counts(story),
        "entries": shown,
    }


def recorded(record: dict[str, Any]) -> dict[str, Any]:
    """The record as the file keeps it, with REQUEST_ID for the hub's request id and TIME for each entry's time."""
    kept = copy.deepcopy(record)
    for entry in kept["exchanges"]:
        masked = []
        for part in (entry.get("result"), entry["request"]["params"]):
            if isinstance(part, dict) and "requestId" in part:
                part["requestId"] = REQUEST_ID
                masked.append("requestId")
        if masked:
            entry["masked"] = sorted(set(masked))
    audit = kept["audit"]
    rows = audit.pop("entries")
    audit["entries"] = [
        {name: int(text) if name == "seq" else text for name, text in row.items() if name != "time"} for row in rows
    ]
    audit["lines"] = log_cmd.lines({**row, "time": TIME} for row in rows)
    audit["masked"] = ["time"]
    return kept


class _Dumper(yaml.SafeDumper):
    """Writes a value that appears twice, such as the bed target before the write, out in full both times."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def dump(record: dict[str, Any]) -> str:
    """The record as YAML, in a stable order."""
    return yaml.dump(recorded(record), Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=200)


def read(path: Path | None = None) -> dict[str, Any]:
    """The recorded scenario, from docs/demo/scenario.yaml by default."""
    target = path or Path(__file__).resolve().parents[2] / SCENARIO_PATH
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return data


def exchange(record: dict[str, Any], name: str) -> dict[str, Any]:
    """One exchange of a record by its id, such as `nozzle-too-hot`."""
    found: dict[str, Any] = next(entry for entry in record["exchanges"] if entry["id"] == name)
    return found
