"""Record the launch film's beats from a real OpenHAL hub into video/data (video/data/README.md).

    uv run --extra mujoco --extra scpi --extra openhal-firmware python video/hub/record.py --cache <folder>

The run makes a temporary home and serves a real hub on a free loopback port, with the simulated
SO-101 from so101-sim.hal.yaml on the mujoco driver. An agent drives the arm through a real
`openhal mcp` stdio session with an agent token. The person acts with the human token over the
REST routes and the live socket the Inspector uses, and confirms each device file's limits in the
temporary home first. Three more devices join in the first beat, each on a simulator the repo
already has, a Klipper printer, a plant waterer board and a bench power supply. Nothing reaches
hardware, and the run never reads a real home or connects to a running hub.

Frames come from the physics thread at a fixed rate, and every hub message is stamped on the same
monotonic clock, in seconds since the recording began.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import datetime as dt
import json
import os
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import menagerie
import mujoco
import numpy
from websockets.asyncio.client import connect

from openhal import __version__
from openhal.client import AsyncClient
from openhal.demo import rig, scenario
from openhal.drivers.mujoco.driver import MujocoDriver
from openhal.drivers.openhal_firmware.simulator import PlantWatererSimulator
from openhal.drivers.scpi.simulator import ScpiServer
from openhal.spec import loads
from openhal.spec.models import DeviceFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARM_FILE = HERE / "so101-sim.hal.yaml"
OUT = ROOT / "video" / "data"
RATE_HZ = 120
PERSON = "owner"
AGENT = "film-agent"
MODEL_ENV = "OPENHAL_SO101_SCENE"
BOARD = "plant-waterer"
ARM_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll")
COLUMNS = (
    "t",
    *ARM_JOINTS,
    "gripper",
    "gripper_jaw",
    *(f"gripper_{part}" for part in ("x", "y", "z", "qw", "qx", "qy", "qz")),
    *(f"tip_{part}" for part in ("x", "y", "z", "qw", "qx", "qy", "qz")),
    *(f"cube_{part}" for part in ("x", "y", "z", "qw", "qx", "qy", "qz")),
    "lag_ms",
)
UNITS = {
    "t": "s on the recording clock",
    "joints": "deg, from the joint angle in the model",
    "gripper": "percent open, 0 at the joint's low end and 100 at its high end",
    "gripper_jaw": "deg, the gripper joint angle itself",
    "positions": "m in the world frame, z up, the arm's base at the origin",
    "quaternions": "w, x, y, z in the world frame",
    "lag_ms": "ms the physics thread ran behind the clock when it took the frame",
}
PLACE = (170.0, -30.0)
ABOVE_MM = 60.0
OUTSIDE = {"x": 320.0, "y": 0.0, "z": 40.0}
FAR = {"x": 220.0, "y": 100.0, "z": 70.0}
SWITCH_S = 0.0005
"""How often Python hands the interpreter between threads, short so the physics thread keeps pace with the hub."""


class RecordingError(RuntimeError):
    """The hub didn't do what the beat needs. The message names the beat and what came back."""


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise RecordingError(message)


def confirmed(text: str, by: str) -> tuple[str, DeviceFile]:
    """The device file text with the person's confirmation, as `openhal file confirm` writes it."""
    lines = [line for line in text.rstrip().splitlines() if not line.startswith("confirmed:")]
    file = loads("\n".join(lines) + "\n")
    stamp = f"confirmed: {{ by: {by}, at: {dt.date.today().isoformat()}, sha256: {file.limits_sha256()} }}"
    final = "\n".join([*lines, stamp]) + "\n"
    file = loads(final)
    expect(not file.unconfirmed(), f"the confirmation left {file.unconfirmed()} unconfirmed")
    return final, file


class Clock:
    """Seconds since the recording began, for frames and messages alike."""

    def __init__(self) -> None:
        self.origin = time.monotonic()

    def now(self) -> float:
        return round(time.monotonic() - self.origin, 4)


class Frames:
    """The arm and the cube at a fixed rate, taken on the physics thread."""

    def __init__(self, driver: MujocoDriver, clock: Clock) -> None:
        world = driver.world
        assert world is not None
        model = world.model
        self.world = world
        self.clock = clock
        steps = (1.0 / RATE_HZ) / world.timestep
        expect(abs(steps - round(steps)) < 1e-6, f"{RATE_HZ} Hz isn't a whole number of {world.timestep} s steps")
        self.every = round(steps)
        self.joints = [int(model.jnt_qposadr[model.joint(name).id]) for name in (*ARM_JOINTS, "gripper")]
        self.low, self.high = (float(value) for value in model.jnt_range[model.joint("gripper").id])
        self.gripper = model.body("gripper").id
        self.cube = model.body("cube").id
        self.tip = model.site("gripperframe").id
        self.raw: list[tuple[Any, ...]] = []
        self.remove = world.watch(self.every, self._take)

    def _take(self, moment: float, data: Any) -> None:
        self.raw.append(
            (
                moment,
                data.qpos[self.joints].copy(),
                data.xpos[self.gripper].copy(),
                data.xquat[self.gripper].copy(),
                data.site_xpos[self.tip].copy(),
                data.site_xmat[self.tip].copy(),
                data.xpos[self.cube].copy(),
                data.xquat[self.cube].copy(),
                self.world.lag_s,
            )
        )

    def rows(self) -> list[list[float]]:
        rows = []
        offset = self.world.origin - self.clock.origin
        for moment, joints, gpos, gquat, tpos, tmat, cpos, cquat, lag in self.raw:
            tquat = numpy.zeros(4)
            mujoco.mju_mat2Quat(tquat, tmat)
            angles = [round(float(value) * 180.0 / 3.141592653589793, 3) for value in joints]
            percent = (float(joints[-1]) - self.low) / (self.high - self.low) * 100.0
            rows.append(
                [
                    round(offset + moment, 4),
                    *angles[:-1],
                    round(percent, 2),
                    angles[-1],
                    *(round(float(value), 5) for value in (*gpos, *gquat, *tpos, *tquat, *cpos, *cquat)),
                    round(max(0.0, lag) * 1000, 1),
                ]
            )
        return rows


class Log:
    """Every hub message, stamped on the recording clock when it arrived."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self.items: list[dict[str, Any]] = []
        self.marks: list[dict[str, Any]] = []

    def add(self, **item: Any) -> dict[str, Any]:
        entry = {"t": self.clock.now(), **item}
        self.items.append(entry)
        return entry

    def mark(self, text: str) -> None:
        self.marks.append({"t": self.clock.now(), "text": text})


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class Session:
    """The agent's MCP session and the person's REST client, with every exchange in the log."""

    def __init__(self, agent: rig.Agent, person: AsyncClient, log: Log) -> None:
        self.agent = agent
        self.person = person
        self.log = log

    async def tool(self, tool: str, arguments: dict[str, Any]) -> Any:
        self.log.add(source="agent", via="mcp", kind="request", tool=tool, arguments=arguments)
        result = await self.agent.client.call_tool(tool, arguments)
        data = result.structured_content
        if isinstance(data, dict) and set(data) == {"result"}:
            data = data["result"]
        if data is None:
            data = " ".join(getattr(block, "text", "") for block in result.content)
        self.log.add(source="hub", via="mcp", kind="response", tool=tool, is_error=result.is_error, result=data)
        expect(not result.is_error, f"the MCP tool {tool} failed: {data}")
        return data

    async def rest(self, method: str, path: str, call: Callable[[], Awaitable[Any]]) -> Any:
        self.log.add(source="person", via="rest", kind="request", method=method, path=path)
        result = _plain(await call())
        self.log.add(source="hub", via="rest", kind="response", method=method, path=path, result=result)
        return result

    async def move_to(self, x: float, y: float, z: float) -> dict[str, Any]:
        args = {axis: {"value": round(value, 1), "unit": "mm"} for axis, value in zip("xyz", (x, y, z), strict=True)}
        decision: dict[str, Any] = await self.tool("action", {"device": "arm", "action": "move_to", "args": args})
        return decision

    async def grip(self, percent: float, condition: str) -> None:
        decision = await self.tool("write", {"device": "arm", "channel": "gripper_goal", "value": percent, "unit": "%"})
        expect(decision["status"] == "done", f"the gripper write ended {decision['status']}: {decision['message']}")
        waited = await self.tool("wait_until", {"condition": condition, "timeout_s": 6, "interval_s": 0.1})
        expect(waited["held"], f"{condition} never held")

    async def cube(self) -> tuple[float, float, float]:
        readings = await self.tool("read_many", {"targets": ["arm.cube_x", "arm.cube_y", "arm.cube_z"]})
        x, y, z = (float(reading["value"]) for reading in readings)
        return x, y, z

    async def pick(self) -> None:
        """Go above the cube, down to it, close the gripper on it, and lift it."""
        x, y, z = await self.cube()
        for height in (ABOVE_MM, z):
            decision = await self.move_to(x, y, height)
            expect(decision["status"] == "done", f"move_to ended {decision['status']}: {decision['message']}")
        await self.grip(0, "arm.gripper < 20 %")
        decision = await self.move_to(x, y, ABOVE_MM)
        expect(decision["status"] == "done", f"the lift ended {decision['status']}: {decision['message']}")


@contextlib.asynccontextmanager
async def beat(log: Log, beats: list[dict[str, Any]], name: str, title: str) -> AsyncIterator[None]:
    start = log.clock.now()
    log.mark(f"beat {name} starts")
    yield
    await asyncio.sleep(1.0)
    end = log.clock.now()
    log.mark(f"beat {name} ends")
    beats.append({"name": name, "title": title, "t_start": start, "t_end": end, "duration_s": round(end - start, 3)})


def offline(file: DeviceFile, driver: Any) -> bool:
    """Whether a device reaches only a simulator, so a run never opens a real port or board."""
    if driver is not None:
        return bool(driver.simulated)
    address = str(file.connect.params.get("port") or file.connect.params.get("resource") or "")
    return address.startswith(("sim:", "TCPIP0::127.0.0.1::"))


async def devices(session: Session, hub: Any, home: Path, supply: ScpiServer) -> None:
    printer_text = scenario.example(scenario.FOLDER, "printer.hal.yaml").read_text(encoding="utf-8")
    board_text = (ROOT / "examples" / "plant-waterer" / "plant-waterer.hal.yaml").read_text(encoding="utf-8")
    supply_text = (ROOT / "openhal" / "drivers" / "scpi" / "examples" / "rigol-dp832.hal.yaml").read_text(
        encoding="utf-8"
    )
    supply_text = supply_text.replace("resource: auto", f'resource: "{supply.resource}"')
    board_text = board_text.replace("openhal-firmware: auto", f'openhal-firmware: "sim:{BOARD}"')
    for name, text in (("printer", printer_text), (BOARD, board_text), ("bench-psu", supply_text)):
        final, file = confirmed(text, PERSON)
        path = home / "devices" / f"{name}.hal.yaml"
        path.write_text(final, encoding="utf-8")
        driver = scenario.SimulatedPrinter(file, scenario.printing()) if name == "printer" else None
        expect(offline(file, driver), f"{name} would reach past its simulator")
        session.log.mark(f"{name} plugged in")
        await hub.add_and_start(file, driver=driver, path=path)
        error = hub.info[file.device_id].last_error
        expect(hub.kernel.devices[file.device_id].connected, f"{name} didn't connect: {error}")
        await asyncio.sleep(1.5)
    listed = await session.tool("list_devices", {})
    connected = sorted(item["id"] for item in listed if item["connected"])
    expect(connected == ["arm", "bench-psu", "plant-waterer", "printer"], f"connected devices are {connected}")


async def pick_and_place(session: Session) -> None:
    await session.pick()
    x, y = PLACE
    for height in (ABOVE_MM, 14.0):
        decision = await session.move_to(x, y, height)
        expect(decision["status"] == "done", f"the carry ended {decision['status']}: {decision['message']}")
    await session.grip(50, "arm.gripper > 45 %")
    decision = await session.move_to(x, y, ABOVE_MM)
    expect(decision["status"] == "done", f"the retreat ended {decision['status']}: {decision['message']}")


async def limit(session: Session) -> None:
    decision = await session.move_to(OUTSIDE["x"], OUTSIDE["y"], OUTSIDE["z"])
    error = decision.get("error") or {}
    expect(decision["status"] == "blocked", f"the move outside the box ended {decision['status']}")
    expect(error.get("name") == "LIMIT_EXCEEDED", f"the block came back as {error}")
    await asyncio.sleep(2.0)


async def approval(session: Session) -> None:
    await session.pick()
    decision = await session.tool("action", {"device": "arm", "action": "drop_in_bin", "args": {}})
    expect(decision["status"] == "pending", f"drop_in_bin ended {decision['status']}, not pending")
    request = decision["request_id"]
    status = await session.tool("get_confirmation_status", {"request_id": request})
    expect(status["requests"][0]["status"] == "pending", f"the request is {status['requests'][0]['status']}")
    await asyncio.sleep(2.0)
    listed = await session.rest("GET", "/v1/confirmations", session.person.confirmations)
    expect(any(item["id"] == request for item in listed), "the person doesn't see the request")
    approved = await session.rest(
        "POST", f"/v1/confirmations/{request}/approve", lambda: session.person.approve(request)
    )
    expect(approved["status"] == "done", f"the approved drop ended {approved['status']}: {approved['message']}")
    status = await session.tool("get_confirmation_status", {"request_id": request})
    await asyncio.sleep(1.5)
    x, y, z = await session.cube()
    expect(75 < x < 165 and -215 < y < -125 and z < 30, f"the cube ended at {x:.0f}, {y:.0f}, {z:.0f} mm")


async def stop(session: Session, driver: MujocoDriver) -> None:
    world = driver.world
    assert world is not None
    move = asyncio.create_task(session.move_to(FAR["x"], FAR["y"], FAR["z"]))
    started = asyncio.Event()
    loop = asyncio.get_running_loop()

    def moving(moment: float, data: Any) -> None:
        if world.motions and not started.is_set():
            loop.call_soon_threadsafe(started.set)

    remove = world.watch(1, moving)
    try:
        await asyncio.wait_for(started.wait(), 10)
    finally:
        remove()
    await asyncio.sleep(0.8)
    expect(bool(world.motions), "the long move ended before the stop")
    report = await session.rest("POST", "/v1/stop", lambda: session.person.stop("stop pressed during a move"))
    arm = next(item for item in report["devices"] if item["device"] == "arm")
    expect(arm["status"] == "safe", f"the arm's safe state came back {arm}")
    decision = await move
    expect(decision["code"] == "stopped", f"the move in flight ended {decision['status']} {decision['code']}")
    status = await session.tool("hub_status", {})
    expect(status["stopped"], "the hub isn't stopped")
    await asyncio.sleep(3.0)


async def live(url: str, token: str, log: Log) -> None:
    async with connect(url.replace("http", "ws", 1) + f"/v1/live?token={token}") as socket:
        async for frame in socket:
            log.add(source="hub", via="live", kind="event", event=json.loads(frame))


async def warm_up(agent: rig.Agent) -> None:
    """One dry run outside the box before the clock starts, so the MCP server has loaded what a block needs.

    A dry run never reaches the device. Without it the first blocked result takes seconds longer
    while the server imports its protocol client, which is the server starting and not the hub.
    """
    args = {axis: {"value": value, "unit": "mm"} for axis, value in OUTSIDE.items()}
    await agent.client.call_tool("dry_run", {"device": "arm", "action": "move_to", "args": args})


def scrub(value: Any, paths: dict[str, str]) -> Any:
    """Every local path replaced with a name, so nothing in the data points at this machine."""
    if isinstance(value, str):
        for path, name in paths.items():
            value = value.replace(path, name)
        return value
    if isinstance(value, dict):
        return {key: scrub(item, paths) for key, item in value.items()}
    if isinstance(value, list):
        return [scrub(item, paths) for item in value]
    return value


async def record(cache: Path, home: Path) -> dict[str, Any]:
    scene = menagerie.scene(cache)
    os.environ[MODEL_ENV] = str(scene)
    person = rig.set_up_home(home, PERSON)
    text, _arm = confirmed(ARM_FILE.read_text(encoding="utf-8"), PERSON)
    (home / "devices" / "arm.hal.yaml").write_text(text, encoding="utf-8")
    supply = ScpiServer()
    beats: list[dict[str, Any]] = []
    try:
        with rig.plugged_in(BOARD, PlantWatererSimulator()):
            async with rig.serving(home) as (hub, url):
                driver = hub.kernel.devices["arm"].driver
                expect(isinstance(driver, MujocoDriver) and hub.kernel.devices["arm"].connected, "the arm is down")
                assert isinstance(driver, MujocoDriver)
                async with AsyncClient(url, person, use_human_token_file=False) as owner:
                    token = (await owner.create_token(AGENT, kind="agent", scope="control_medium")).token
                    async with rig.mcp_session(url, token, home) as agent:
                        await warm_up(agent)
                        clock = Clock()
                        log = Log(clock)
                        session = Session(agent, owner, log)
                        listener = asyncio.create_task(live(url, person, log))
                        frames = Frames(driver, clock)
                        try:
                            await asyncio.sleep(1.0)
                            async with beat(log, beats, "devices", "Three more devices connect"):
                                await devices(session, hub, home, supply)
                            async with beat(log, beats, "pick-and-place", "The agent picks the cube and places it"):
                                await pick_and_place(session)
                            async with beat(log, beats, "limit", "A move outside the workspace box"):
                                await limit(session)
                            async with beat(log, beats, "approval", "The drop into the bin waits for a person"):
                                await approval(session)
                            async with beat(log, beats, "stop", "STOP during a move"):
                                await stop(session, driver)
                        finally:
                            frames.remove()
                            listener.cancel()
                            with contextlib.suppress(asyncio.CancelledError, Exception):
                                await listener
                        rows = frames.rows()
    finally:
        supply.close()
    return {
        "beats": beats,
        "rows": rows,
        "messages": log.items,
        "marks": log.marks,
        "timestep": frames.world.timestep,
        "lag_ms": max((row[-1] for row in rows), default=0.0),
        "paths": {str(scene.parent): "MODEL_DIR"},
    }


def write(result: dict[str, Any], out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    index = []
    for number, item in enumerate(result["beats"], start=1):
        start, end = item["t_start"], item["t_end"]
        rows = [row for row in result["rows"] if start <= row[0] <= end]
        messages = [message for message in result["messages"] if start <= message["t"] <= end]
        marks = [mark for mark in result["marks"] if start <= mark["t"] <= end]
        name = f"beat-{number}-{item['name']}.json"
        body = {**item, "frames": {"rate_hz": RATE_HZ, "columns": list(COLUMNS), "rows": rows}, "messages": messages}
        body["marks"] = marks
        path = out / name
        path.write_text(json.dumps(body, separators=(",", ":")) + "\n", encoding="utf-8")
        written.append(path)
        index.append({**item, "file": name, "frames": len(rows), "messages": len(messages)})
    session = {
        "recorded_with": "uv run --extra mujoco --extra scpi --extra openhal-firmware python video/hub/record.py",
        "recorded_on": dt.date.today().isoformat(),
        "openhal": __version__,
        "mujoco": mujoco.__version__,
        "clock": "seconds since the recording began, one monotonic clock for frames and messages",
        "model": {
            "source": "MuJoCo Menagerie robotstudio_so101",
            "commit": menagerie.COMMIT,
            "license": "Apache-2.0",
            "scene": "video/hub/scene.xml",
            "device_file": "video/hub/so101-sim.hal.yaml",
        },
        "principals": {"person": f"human:{PERSON}", "agent": f"agent:{AGENT}"},
        "frames": {
            "rate_hz": RATE_HZ,
            "timestep_s": result["timestep"],
            "columns": list(COLUMNS),
            "units": UNITS,
            "max_lag_ms": result["lag_ms"],
        },
        "scene": {
            "floor": {"z_m": 0.0},
            "cube": {"size_m": 0.025, "mass_kg": 0.02, "start_m": [0.2, 0.09, 0.0125], "start_yaw_deg": 26.6},
            "bin": {"center_m": [0.12, -0.17, 0.0], "inside_m": [0.082, 0.082], "wall_height_m": 0.04},
        },
        "beats": index,
    }
    path = out / "session.json"
    path.write_text(json.dumps(session, indent=2) + "\n", encoding="utf-8")
    return [path, *written]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Record the film's beats from a real hub.")
    parser.add_argument("--cache", type=Path, required=True, help="A folder for the Menagerie model.")
    parser.add_argument("--out", type=Path, default=OUT, help="Where the JSON goes, video/data by default.")
    parser.add_argument("--home", type=Path, help="A scratch folder for the temporary home.")
    options = parser.parse_args(argv)
    sys.setswitchinterval(SWITCH_S)
    with tempfile.TemporaryDirectory(prefix="openhal-film-", dir=options.home) as folder:
        home = Path(folder)
        result = asyncio.run(record(options.cache, home))
    paths = {str(home.resolve()): "OPENHAL_HOME", str(home): "OPENHAL_HOME", **result["paths"]}
    result["messages"] = scrub(result["messages"], paths)
    for path in write(result, options.out):
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  {path.stat().st_size} bytes")
    print(f"max lag {result['lag_ms']} ms")


if __name__ == "__main__":
    sys.exit(main())
