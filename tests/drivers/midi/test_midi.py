"""The midi driver against the fake mido backend and the simulated pad controller."""

from __future__ import annotations

from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.midi.conformance import FILE
from openhal.drivers.midi.driver import MidiDriver
from openhal.drivers.midi.simulator import PORT, FakeMidiBackend, SimulatedController
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "midi" / "examples"
WHO = human("tester")


def make(file: DeviceFile = FILE, *controllers: SimulatedController) -> tuple[MidiDriver, SimulatedController]:
    controller = controllers[0] if controllers else SimulatedController()
    return MidiDriver(file, backend=FakeMidiBackend(controller, *controllers[1:])), controller


def device(channels: str, connect: str = '{ midi: "Sim Pads" }') -> DeviceFile:
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


async def kernel_for(driver: MidiDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { unit: dimensionless }", "needs a map"),
        ("read:\n  x: { unit: dimensionless, map: { cc: 1, note: 2 } }", "exactly one"),
        ("read:\n  x: { unit: dimensionless, map: {} }", "exactly one"),
        ("read:\n  x: { unit: dimensionless, map: { cc: 128 } }", "less than or equal to 127"),
        ("read:\n  x: { unit: dimensionless, map: { cc: 1, channel: 17 } }", "less than or equal to 16"),
        ("read:\n  x: { unit: V, map: { cc: 1 } }", "dimensionless"),
        ("read:\n  x: { type: string, map: { cc: 1 } }", "numbers or bools"),
        ("read:\n  x: { type: bool, map: { pitchwheel: true } }", "cc or note"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MidiDriver(loads(f"device: T\nconnect: {{ midi: auto }}\n{channels}\n"))


# ---------------------------------------------------------------------- reads


async def test_reads_are_unknown_until_controls_move() -> None:
    driver, controller = make()
    await driver.connect()
    knob = await driver.read("knob_1")
    assert knob.value is None
    assert knob.unit == "dimensionless"
    controller.turn(1, 100)
    controller.turn(2, 127)
    controller.press(36, 90)
    assert (await driver.read("knob_1")).value == 100.0
    assert (await driver.read("knob_2")).value == pytest.approx(100.0)
    assert (await driver.read("pad_1")).value is True
    controller.release(36)
    assert (await driver.read("pad_1")).value is False
    controller.press(36, 0)
    assert (await driver.read("pad_1")).value is False, "note on with velocity 0 is note off"
    controller.turn(1, 5, channel=3)
    assert (await driver.read("knob_1")).value == 100.0, "other MIDI channels are ignored"


async def test_cc_bools_pitch_bend_program_and_channels() -> None:
    channels = (
        "read:\n"
        "  sustain: { type: bool, map: { cc: 64 } }\n"
        "  bend: { unit: percent, map: { pitchwheel: true } }\n"
        "  raw_bend: { unit: dimensionless, range: [-100, 100], map: { pitchwheel: true } }\n"
        "  other: { unit: dimensionless, map: { cc: 7, channel: 10 } }"
    )
    driver, controller = make(device(channels))
    await driver.connect()
    controller.turn(64, 63)
    assert (await driver.read("sustain")).value is False
    controller.turn(64, 64)
    assert (await driver.read("sustain")).value is True
    controller.bend(8191)
    assert (await driver.read("bend")).value == pytest.approx(100.0)
    assert (await driver.read("raw_bend")).suspect is True
    controller.bend(-8192)
    assert (await driver.read("bend")).value == pytest.approx(-100.0)
    controller.turn(7, 42, channel=9)
    assert (await driver.read("other")).value == 42.0


# ---------------------------------------------------------------------- writes


async def test_writes_send_midi_messages() -> None:
    channels = (
        "write:\n"
        "  led: { type: bool, map: { note: 36, velocity: 5 } }\n"
        "  colour: { unit: dimensionless, min: 0, max: 127, map: { note: 37 } }\n"
        "  cutoff: { unit: percent, min: 0, max: 100, map: { cc: 74, channel: 2 } }\n"
        "  bypass: { type: bool, map: { cc: 80, on: 100, off: 1 } }\n"
        "  patch: { unit: dimensionless, min: 0, max: 127, map: { program: true } }\n"
        "  bend: { unit: percent, min: -100, max: 100, map: { pitchwheel: true } }"
    )
    driver, controller = make(device(channels))
    kernel = await kernel_for(driver)
    assert (await driver.read("led")).value is None
    for channel, value in (
        ("led", True),
        ("colour", "21 dimensionless"),
        ("cutoff", "50 %"),
        ("bypass", True),
        ("patch", "3 dimensionless"),
        ("bend", "-50 %"),
        ("led", False),
    ):
        decision = await kernel.execute(Write(device="t", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    sent = [str(message) for message in controller.received]
    assert sent == [
        "note_on channel=0 note=36 velocity=5 time=0",
        "note_on channel=0 note=37 velocity=21 time=0",
        "control_change channel=1 control=74 value=64 time=0",
        "control_change channel=0 control=80 value=100 time=0",
        "program_change channel=0 program=3 time=0",
        "pitchwheel channel=0 pitch=-4096 time=0",
        "note_off channel=0 note=36 velocity=0 time=0",
    ]
    assert controller.leds == {36: 0, 37: 21}
    cutoff = await driver.read("cutoff")
    assert cutoff.value == pytest.approx(64 * 100 / 127)
    assert (await driver.read("led")).value is False


async def test_writes_fail_when_unplugged() -> None:
    driver, controller = make()
    kernel = await kernel_for(driver)
    controller.unplug()
    health = await driver.health()
    assert health.connected is False
    assert "is gone" in health.detail
    decision = await kernel.execute(Write(device="conformance-midi", channel="pad_1_led", value=True), WHO)
    assert decision.status in ("failed", "blocked")
    assert controller.received == []


async def test_out_of_range_raw_values_fail() -> None:
    channels = "write:\n  big: { unit: dimensionless, min: 0, max: 200, map: { cc: 1 } }"
    driver, controller = make(device(channels))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="big", value="150 dimensionless"), WHO)
    assert decision.status == "failed"
    assert "0 to 127" in decision.message
    assert controller.received == []


# ---------------------------------------------------------------------- ports


async def test_port_selection() -> None:
    other = SimulatedController(name="Other Synth")
    pads = SimulatedController()
    with pytest.raises(DriverError, match="2 MIDI input ports"):
        await make(device("read:\n  k: { unit: dimensionless, map: { cc: 1 } }", "{ midi: auto }"), pads, other)[
            0
        ].connect()
    with pytest.raises(DriverError, match="0 MIDI input ports match"):
        await make(device("read:\n  k: { unit: dimensionless, map: { cc: 1 } }", "{ midi: Nope }"), pads)[0].connect()
    with pytest.raises(DriverError, match="No MIDI output port named"):
        await make(device("write:\n  l: { type: bool, map: { note: 1 } }", "{ midi: auto, output: Gone }"), pads)[
            0
        ].connect()
    driver, _ = make(device("read:\n  k: { unit: dimensionless, map: { cc: 1 } }", "{ midi: auto }"), pads)
    await driver.connect()
    assert (await driver.identify())["input"] == PORT
    assert (await driver.health()).connected


async def test_connect_fails_when_unplugged_and_recovers() -> None:
    controller = SimulatedController(plugged=False)
    driver, _ = make(FILE, controller)
    with pytest.raises(DriverError, match="0 MIDI input ports match"):
        await driver.connect()
    assert (await driver.health()).connected is False
    with pytest.raises(DriverError, match="not open"):
        await driver.read("knob_1")
    with pytest.raises(DriverError, match="not open"):
        await driver.read("pad_1_led")
    controller.plug_in()
    await driver.connect()
    assert (await driver.health()).connected


async def test_open_errors_become_driver_errors() -> None:
    class Broken(FakeMidiBackend):
        def open_input(self, name: str | None = None, callback: object = None, **_: object) -> object:
            raise OSError("rtmidi: error opening port")

    driver = MidiDriver(FILE, backend=Broken(SimulatedController()))
    with pytest.raises(DriverError, match="error opening port"):
        await driver.connect()


# ---------------------------------------------------------------------- discover and describe


async def test_discover_lists_ports() -> None:
    found = await MidiDriver.discover(backend=FakeMidiBackend(SimulatedController()))
    assert [(item.address, item.label) for item in found] == [(PORT, f"{PORT} (input and output)")]


async def test_describe_proposes_moved_controls() -> None:
    driver, controller = make()
    assert await driver.describe(listen_s=0) is None
    await driver.connect()
    controller.turn(3, 10)
    controller.press(40)
    controller.turn(9, 1, channel=4)
    described = await driver.describe(listen_s=0)
    assert described is not None
    assert described["read"] == {
        "cc_3": {"unit": "dimensionless", "stream": True, "range": [0, 127], "map": {"cc": 3}},
        "cc_9_ch5": {"unit": "dimensionless", "stream": True, "range": [0, 127], "map": {"cc": 9, "channel": 5}},
        "note_40": {"unit": "dimensionless", "stream": True, "range": [0, 127], "map": {"note": 40}},
    }
    MidiDriver(DeviceFile.model_validate({"device": "x", "connect": {"midi": "auto"}, "read": described["read"]}))


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    MidiDriver(report.file)
