"""The Arduino library itself, built for this computer and driven by the real driver and kernel.

The sketches compile against a small stand-in for the Arduino core (firmware/arduino/OpenHAL/extras/host),
so the C++ that runs on a board is the C++ under test here. Skipped when no C++ compiler is installed.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from openhal.conformance import ConformanceCase, run
from openhal.drivers.base import Driver, DriverError
from openhal.drivers.openhal_firmware import protocol
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.kernel import Action, Kernel, Write, human
from openhal.spec import DeviceFile, loads
from openhal.spec.loader import from_data

LIBRARY = Path(__file__).resolve().parents[2] / "firmware" / "arduino" / "OpenHAL"
COMPILER = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
pytestmark = pytest.mark.skipif(COMPILER is None, reason="no C++ compiler")


def build(example: str, out: Path, *defines: str) -> Path:
    binary = out / example
    subprocess.run(
        [
            str(COMPILER),
            "-std=c++11",
            "-Wall",
            "-Wextra",
            "-Werror",
            *(f"-D{define}" for define in defines),
            f"-I{LIBRARY / 'extras' / 'host'}",
            f"-I{LIBRARY / 'src'}",
            "-x",
            "c++",
            str(LIBRARY / "examples" / example / f"{example}.ino"),
            "-x",
            "none",
            str(LIBRARY / "src" / "OpenHAL.cpp"),
            str(LIBRARY / "extras" / "host" / "host_main.cpp"),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run([str(binary)], input=b"", capture_output=True, timeout=30, check=True)
    return binary


@pytest.fixture(scope="module")
def binaries(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    out = tmp_path_factory.mktemp("firmware")
    return {
        "DeskFan": build("DeskFan", out),
        "LedStrip": build("LedStrip", out),
        "ServoArm": build("ServoArm", out),
        "SoilPump": build("SoilPump", out, "PUMP_MAX_RUN_MS=300"),
        "PlantWaterer": build("PlantWaterer", out),
    }


class ProcessTransport:
    """A line transport to a host-built sketch, as if it were a board on a serial port."""

    def __init__(self, binary: Path, env: dict[str, str] | None = None, pins: Path | None = None) -> None:
        self.binary = binary
        self.env = env or {}
        self.pins = pins
        self.process: asyncio.subprocess.Process | None = None

    async def connect(self) -> None:
        log = self.pins.open("ab") if self.pins is not None else asyncio.subprocess.DEVNULL
        self.process = await asyncio.create_subprocess_exec(
            str(self.binary),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=log,
            env={**os.environ, "OPENHAL_HOST_A0": "480", "OPENHAL_HOST_A2": "450", **self.env},
        )

    async def write_line(self, line: str) -> None:
        if self.process is None or self.process.stdin is None or self.process.returncode is not None:
            raise ConnectionError("The board is gone.")
        try:
            self.process.stdin.write(line.encode("ascii"))
            await self.process.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise ConnectionError("The board is gone.") from exc

    async def read_line(self) -> str:
        if self.process is None or self.process.stdout is None:
            raise ConnectionError("The board is gone.")
        line = await self.process.stdout.readline()
        if not line:
            raise ConnectionError("The board is gone.")
        return line.decode("ascii")

    def pause(self) -> None:
        if self.process is not None:
            self.process.send_signal(signal.SIGSTOP)

    async def close(self) -> None:
        if self.process is not None and self.process.returncode is None:
            self.process.kill()
            await self.process.wait()
        self.process = None


def driver_for(
    file: DeviceFile, binary: Path, env: dict[str, str] | None = None, pins: Path | None = None
) -> OpenHalFirmwareDriver:
    driver = OpenHalFirmwareDriver(file)
    driver._make_transport = lambda: ProcessTransport(binary, env, pins)  # type: ignore[method-assign]
    return driver


def transport_of(driver: Driver) -> ProcessTransport:
    assert isinstance(driver, OpenHalFirmwareDriver)
    link = driver._link
    assert link is not None
    transport = link.transport
    assert isinstance(transport, ProcessTransport)
    return transport


DESK_FAN = """
device: Desk fan on the bench
id: real-fan
connect: { openhal-firmware: /dev/null, timeout_s: 0.5 }
read:
  temperature: { unit: degC, range: [-20, 80] }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 20 }
safe_state: { fan_speed: 0 }
watchdog: { heartbeat: 1 s, on_loss: safe_state }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

SOIL_PUMP = """
device: Plant waterer
id: waterer
connect: { openhal-firmware: /dev/null, timeout_s: 0.5 }
read:
  soil_moisture: { unit: percent }
write:
  pump: { type: bool }
safe_state: { pump: false }
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_the_compiled_sketch_passes_conformance(binaries: dict[str, Path]) -> None:
    async def unplug(driver: Driver) -> None:
        await transport_of(driver).close()

    async def freeze(driver: Driver) -> None:
        transport_of(driver).pause()

    case = ConformanceCase(
        name="openhal-firmware (Arduino library, host build)",
        file=loads(DESK_FAN),
        make=lambda file: driver_for(file, binaries["DeskFan"]),
        break_connection=unplug,
        make_slow=freeze,
    )
    report = await run(case)
    failures = [f"{result.name}: {result.detail}" for result in report.results if not result.ok and not result.skipped]
    assert report.ok, "\n".join(failures)
    assert not [result.name for result in report.results if result.skipped]


@pytest.mark.parametrize("example", ["DeskFan", "LedStrip", "ServoArm", "SoilPump", "PlantWaterer"])
async def test_every_example_describes_itself_into_a_valid_read_only_file(
    binaries: dict[str, Path], example: str
) -> None:
    driver = driver_for(loads(DESK_FAN), binaries[example])
    await driver.connect()
    described = await driver.describe()
    await driver.close()
    assert described is not None
    draft = from_data({"device": described.pop("device")["name"], "connect": {"openhal-firmware": "auto"}, **described})
    assert draft.write or draft.actions, f"{example} has no outputs or actions"
    assert not draft.writable, "a self-described file stays read-only until a person confirms it"
    assert all(entry.suggested for entry in [*draft.write.values(), *draft.actions.values()])
    if example == "PlantWaterer":
        assert draft.read["tank"].values == ["empty", "ok"]
        duration = draft.actions["water"].args["duration"]
        assert (duration.unit, duration.min, duration.max) == ("s", 1, 30)
        assert "pump" not in draft.write, "an internal output is never offered to the hub"


async def test_servo_limits_come_from_the_sketch(binaries: dict[str, Path]) -> None:
    driver = driver_for(loads(DESK_FAN), binaries["ServoArm"])
    await driver.connect()
    described = await driver.describe()
    await driver.close()
    assert described is not None
    assert described["write"]["angle"]["min"] == 20
    assert described["write"]["angle"]["max"] == 160
    assert described["safe_state"] == {"angle": 90}


async def test_kernel_writes_and_stop_reach_the_real_firmware(binaries: dict[str, Path]) -> None:
    now = [10_000.0]
    kernel = Kernel(clock=lambda: now[0])
    driver = driver_for(loads(DESK_FAN), binaries["DeskFan"])
    kernel.register(loads(DESK_FAN), driver)
    await kernel.connect("real-fan")
    now[0] += 60
    who = human("tester")
    done = await kernel.execute(Write(device="real-fan", channel="fan_speed", value="60 %"), who)
    assert done.status == "done", done.message
    assert (await driver.read("fan_speed")).value == 60
    blocked = await kernel.execute(Write(device="real-fan", channel="fan_speed", value="150 %"), who)
    assert blocked.status == "blocked"
    result = await kernel.stop_all(who, "test")
    assert result.devices[0].status == "safe"
    assert (await driver.read("fan_speed")).value == 0
    await driver.close()


async def test_firmware_refuses_what_the_hub_would_never_send(binaries: dict[str, Path]) -> None:
    """The second wall. Even a raw line that skips the hub can't push the fan past 100 %."""
    transport = ProcessTransport(binaries["DeskFan"])
    await transport.connect()
    replies = {}
    for seq, args in ((1, ("fan_speed", "150")), (2, ("fan_speed", "-5")), (3, ("fan_speed", "1e3"))):
        await transport.write_line(protocol.encode(seq, "WRITE", *args))
        while True:
            message = protocol.decode(await asyncio.wait_for(transport.read_line(), 2))
            if message.seq == seq:
                replies[seq] = message
                break
    await transport.write_line("4 WRITE fan_speed 60*00\n")
    await transport.write_line(protocol.encode(5, "READ", "fan_speed"))
    while True:
        message = protocol.decode(await asyncio.wait_for(transport.read_line(), 2))
        if message.seq == 5:
            break
    await transport.close()
    assert replies[1].args == ("limit", "fan_speed", "max", "100")
    assert replies[2].args == ("limit", "fan_speed", "min", "0")
    assert replies[3].args[0] == "format"
    assert message.args == ("fan_speed", "0"), "a line with a bad checksum must not change anything"


async def test_firmware_falls_safe_when_heartbeats_stop(binaries: dict[str, Path]) -> None:
    transport = ProcessTransport(binaries["DeskFan"])
    await transport.connect()
    await transport.write_line(protocol.encode(1, "WRITE", "fan_speed", "40"))
    seen: list[protocol.Message] = []

    async def collect() -> None:
        while not any(message.verb == "SAFE" for message in seen):
            seen.append(protocol.decode(await transport.read_line()))

    await asyncio.wait_for(collect(), 4)
    await transport.close()
    assert any(message.args == ("heartbeat_lost",) for message in seen)


async def test_pump_switches_itself_off(binaries: dict[str, Path]) -> None:
    kernel = Kernel()
    driver = driver_for(loads(SOIL_PUMP), binaries["SoilPump"])
    kernel.register(loads(SOIL_PUMP), driver)
    await kernel.connect("waterer")
    who = human("tester")
    decision = await kernel.execute(Write(device="waterer", channel="pump", value=True), who)
    assert decision.status == "done", decision.message
    assert (await driver.read("pump")).value is True
    await asyncio.sleep(0.6)
    assert (await driver.read("pump")).value is False
    assert "pump_timeout" in driver.safe_reports
    await driver.close()


PLANT_WATERER = Path(__file__).resolve().parents[2] / "examples" / "plant-waterer"


def plant_waterer() -> DeviceFile:
    """The example's own device file, pointed at the host build and confirmed for the test."""
    text = (PLANT_WATERER / "plant-waterer.hal.yaml").read_text()
    text = text.replace("connect: { openhal-firmware: auto, boot_s: 2 }", "connect: { openhal-firmware: /dev/null }")
    return loads(text + "confirmed: { by: tester, at: 2026-10-24 }\n")


def test_the_example_sketch_is_the_library_example() -> None:
    example = (PLANT_WATERER / "plant-waterer.ino").read_text()
    assert example == (LIBRARY / "examples" / "PlantWaterer" / "PlantWaterer.ino").read_text()


async def test_the_plant_waterer_waters_only_within_its_limits(binaries: dict[str, Path], tmp_path: Path) -> None:
    pins = tmp_path / "pins.log"
    file = plant_waterer()
    kernel = Kernel()
    driver = driver_for(file, binaries["PlantWaterer"], pins=pins)
    kernel.register(file, driver)
    await kernel.connect("plant-waterer")
    who = human("tester")
    tank = await driver.read("tank")
    assert tank.value == "ok"
    kernel.note_reading("plant-waterer", tank)
    long = Action(device="plant-waterer", action="water", args={"duration": {"value": 120, "unit": "s"}})
    blocked = await kernel.execute(long, who)
    assert (blocked.status, blocked.code) == ("blocked", "above_max")
    assert "pin 7 = 1" not in pins.read_text()
    short = Action(device="plant-waterer", action="water", args={"duration": {"value": 1, "unit": "s"}})
    done = await kernel.execute(short, who)
    assert done.status == "done", done.message
    assert "pin 7 = 1" in pins.read_text()
    await asyncio.sleep(1.3)
    assert pins.read_text().rstrip().endswith("pin 7 = 0"), "the board stops the pump when the time is up"
    with pytest.raises(DriverError, match="unknown pump"):
        await driver._require_link().request("WRITE", "pump", "1")
    await driver.close()


async def test_the_board_refuses_to_pump_from_an_empty_tank(binaries: dict[str, Path], tmp_path: Path) -> None:
    pins = tmp_path / "pins.log"
    file = plant_waterer()
    kernel = Kernel()
    driver = driver_for(file, binaries["PlantWaterer"], env={"OPENHAL_HOST_D4": "1"}, pins=pins)
    kernel.register(file, driver)
    await kernel.connect("plant-waterer")
    tank = await driver.read("tank")
    assert tank.value == "empty"
    kernel.note_reading("plant-waterer", tank)
    action = Action(device="plant-waterer", action="water", args={"duration": {"value": 5, "unit": "s"}})
    blocked = await kernel.execute(action, human("tester"))
    assert (blocked.code, blocked.limit) == ("interlock", {"interlock": "pump can't run while tank is empty"})
    with pytest.raises(DriverError, match="interlock tank_empty"):
        await driver._require_link().request("ACT", "water", "duration", "5")
    assert "pin 7 = 1" not in pins.read_text()
    await driver.close()
