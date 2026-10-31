"""The hid driver against the fake hidapi module and the simulated macropad."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.hid import descriptor
from openhal.drivers.hid.conformance import FILE
from openhal.drivers.hid.driver import HidDriver
from openhal.drivers.hid.simulator import DESCRIPTOR, FakeHid, SimulatedMacropad
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "hid" / "examples"
WHO = human("tester")


def make(file: DeviceFile = FILE, *pads: SimulatedMacropad) -> tuple[HidDriver, SimulatedMacropad]:
    pad = pads[0] if pads else SimulatedMacropad()
    return HidDriver(file, hid_module=FakeHid(pad, *pads[1:])), pad


def device(channels: str, connect: str = "{ hid: auto, vid: 0x1209, pid: 0x4d48 }") -> DeviceFile:
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


async def kernel_for(driver: HidDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


async def settle(condition: object) -> None:
    assert callable(condition)
    for _ in range(100):
        if condition():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never held")


def test_descriptor_parses_every_field() -> None:
    parsed = descriptor.parse(DESCRIPTOR)
    assert parsed.uses_report_ids
    summary = [(f.section, f.report, f.bit, f.size, f.name) for f in parsed.fields]
    assert summary == [
        ("input", 1, 0, 1, "button_1"),
        ("input", 1, 1, 1, "button_2"),
        ("input", 1, 2, 1, "button_3"),
        ("input", 1, 3, 1, "button_4"),
        ("input", 1, 8, 8, "dial"),
        ("input", 1, 16, 16, "slider"),
        ("output", 2, 0, 1, "num_lock"),
        ("output", 2, 1, 1, "caps_lock"),
        ("output", 2, 2, 1, "scroll_lock"),
        ("output", 2, 8, 8, "field_r2_b8"),
        ("feature", 3, 0, 8, "field_r3_b0"),
    ]
    assert parsed.fields[5].logical_max == 1023


def test_descriptor_proposals_load_as_a_device_file() -> None:
    proposal = descriptor.propose(descriptor.parse(DESCRIPTOR))
    assert proposal["read"]["button_4"] == {"type": "bool", "map": {"report": 1, "byte": 0, "mask": 8}}
    assert proposal["read"]["slider"] == {
        "unit": "dimensionless",
        "map": {"report": 1, "byte": 2, "format": "uint16"},
        "range": [0, 1023],
    }
    assert proposal["write"]["field_r2_b8"]["suggested"] is True
    assert proposal["write"]["field_r2_b8"]["max"] == 255
    assert "feature report 3" in proposal["notes"]
    file = DeviceFile.model_validate(
        {"device": "x", "connect": {"hid": "auto"}, "read": proposal["read"], "write": proposal["write"]}
    )
    assert not file.writable
    HidDriver(file)


def test_descriptor_edge_cases() -> None:
    with pytest.raises(ValueError, match="truncated"):
        descriptor.parse(bytes.fromhex("0501a1018501261f"))
    pushed = descriptor.parse(bytes.fromhex("050975019501a4050109308102b409018102"))
    assert [field.usage_page for field in pushed.fields] == [1, 9]
    long_item = descriptor.parse(bytes.fromhex("fe0200aabb0509090175019501810295078103"))
    assert len(long_item.fields) == 1
    odd = descriptor.propose(descriptor.parse(bytes.fromhex("050109307503950181020931750c95018102")))
    assert "read" not in odd
    assert "bits" in odd["notes"]


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { type: bool }", "needs a map"),
        ("read:\n  x: { type: bool, map: { report: 256 } }", "less than or equal to 255"),
        ("read:\n  x: { type: string, map: { report: 1 } }", "numbers, bools or enums"),
        ("read:\n  x: { type: bool, map: { report: 2, kind: output } }", "Make it a write channel"),
        ("write:\n  x: { type: bool, map: { report: 2 } }", "kind: output"),
        ("read:\n  x: { type: bool, map: { report: 1, mask: 256 } }", "wider than"),
        ("read:\n  x: { unit: W, map: { report: 1, scale: 0 } }", "zero"),
        ("read:\n  x: { unit: W, map: { report: 1, byte: 70 } }", "report_length"),
        ("read:\n  x: { type: enum, values: [a], map: { report: 1 } }", "values for a"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        HidDriver(device(channels))


@pytest.mark.parametrize(
    ("connect", "message"),
    [("{ hid: auto, vid: 70000 }", "less than or equal to 65535"), ("{ hid: auto, vid: zz }", "invalid literal")],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        HidDriver(device("read:\n  x: { type: bool, map: { report: 1 } }", connect))


async def test_input_reports_stream_into_reads() -> None:
    driver, pad = make()
    await driver.connect()
    button = await driver.read("button_1")
    assert button.value is None
    pad.turn(dial=255, slider=1000)
    pad.press(4)
    await settle(lambda: driver._latest.get(1, (b"",))[0][:1] == b"\x08")
    assert (await driver.read("button_4")).value is True
    assert (await driver.read("button_1")).value is False
    assert (await driver.read("dial")).value == pytest.approx(100.0)
    assert (await driver.read("slider")).value == 1000.0
    pad.release(4)
    await settle(lambda: driver._latest[1][0][:1] == b"\x00")
    assert (await driver.read("button_4")).value is False
    await driver.close()


async def test_feature_reports_signed_formats_and_range() -> None:
    channels = (
        "read:\n"
        "  mode: { unit: dimensionless, map: { report: 3, kind: feature } }\n"
        "  signed: { unit: dimensionless, range: [0, 10], map: { report: 1, byte: 1, format: int8 } }\n"
        "  big: { unit: dimensionless, map: { report: 1, byte: 2, format: uint16, byteorder: big } }\n"
        "  short: { unit: dimensionless, map: { report: 1, byte: 3, format: uint32 } }\n"
        "  bad: { unit: dimensionless, map: { report: 4, kind: feature } }"
    )
    driver, pad = make(device(channels))
    await driver.connect()
    assert (await driver.read("mode")).value == 1.0
    pad.turn(dial=0xFE, slider=0x0102)
    await settle(lambda: 1 in driver._latest)
    signed = await driver.read("signed")
    assert signed.value == -2.0
    assert signed.suspect is True
    assert (await driver.read("big")).value == float(0x0201)
    with pytest.raises(DriverError, match="can't be decoded"):
        await driver.read("short")
    with pytest.raises(DriverError, match="feature report 4 failed"):
        await driver.read("bad")


async def test_devices_without_report_ids() -> None:
    channels = "read:\n  first: { unit: dimensionless, map: { byte: 0 } }"
    driver, pad = make(device(channels))
    await driver.connect()
    pad.turn(dial=9)
    await settle(lambda: 0 in driver._latest)
    assert (await driver.read("first")).value == 1.0, "without report ids the first byte is data"


async def test_output_writes_change_only_their_bits() -> None:
    driver, pad = make()
    kernel = await kernel_for(driver)
    assert (await driver.read("led_1")).value is None
    for channel, value in (("led_1", True), ("led_3", True), ("brightness", "200 dimensionless"), ("led_1", False)):
        decision = await kernel.execute(Write(device="conformance-hid", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert pad.writes == [bytes([2, 1, 0]), bytes([2, 5, 0]), bytes([2, 5, 200]), bytes([2, 4, 200])]
    assert (pad.leds, pad.brightness) == (4, 200)
    assert (await driver.read("led_3")).value is True
    decision = await kernel.execute(Write(device="conformance-hid", channel="mode", value="party"), WHO)
    assert decision.status == "done"
    assert pad.features == [bytes([3, 2])]
    assert (await driver.read("mode")).value == "party"


async def test_fill_values_and_refused_reports() -> None:
    channels = (
        "write:\n"
        "  level: { unit: dimensionless, min: 0, max: 300, map: { report: 2, kind: output, byte: 1, fill: [7, 0] } }\n"
        "  wrong: { type: bool, map: { report: 9, kind: output } }\n"
        "  nibble: { unit: dimensionless, min: 0, max: 20, map: { report: 2, kind: output, mask: 0xF0 } }"
    )
    driver, pad = make(device(channels))
    kernel = await kernel_for(driver)
    await kernel.execute(Write(device="t", channel="level", value="9 dimensionless"), WHO)
    assert pad.writes == [bytes([2, 7, 9])]
    decision = await kernel.execute(Write(device="t", channel="level", value="300 dimensionless"), WHO)
    assert decision.status == "failed"
    assert "doesn't fit" in decision.message
    decision = await kernel.execute(Write(device="t", channel="nibble", value="16 dimensionless"), WHO)
    assert decision.status == "failed"
    await kernel.execute(Write(device="t", channel="nibble", value="15 dimensionless"), WHO)
    assert pad.writes[-1] == bytes([2, 0xF7, 9])
    decision = await kernel.execute(Write(device="t", channel="wrong", value=True), WHO)
    assert decision.status == "failed"
    assert "returned an error for output report 9" in decision.message


async def test_selection_and_open_errors() -> None:
    first = SimulatedMacropad()
    second = SimulatedMacropad(path=b"sim-hid-0002", serial="MP-0002")
    channels = "read:\n  b: { type: bool, map: { report: 1, mask: 1 } }"
    with pytest.raises(DriverError, match="2 HID interfaces match"):
        await make(device(channels), first, second)[0].connect()
    with pytest.raises(DriverError, match="0 HID interfaces match"):
        await make(device(channels, "{ hid: Keyboard, vid: 0x1209 }"), first)[0].connect()
    driver, _ = make(device(channels, "{ hid: macro, serial: MP-0002 }"), first, second)
    await driver.connect()
    assert (await driver.identify())["serial"] == "MP-0002"
    other, _ = make(device(channels, '{ hid: auto, path: "sim-hid-0002" }'), first, second)
    with pytest.raises(DriverError, match="Another program may hold it"):
        await other.connect()
    await driver.close()
    await other.connect()
    assert (await other.health()).connected


async def test_unplug_is_noticed_and_reopen_works() -> None:
    driver, pad = make()
    kernel = await kernel_for(driver)
    assert (await driver.health()).connected
    pad.unplug()
    await settle(lambda: not driver.connected)
    health = await driver.health()
    assert health.connected is False
    assert "stopped sending replies" in health.detail
    with pytest.raises(DriverError, match="reopen"):
        await driver.read("button_1")
    decision = await kernel.execute(Write(device="conformance-hid", channel="led_1", value=True), WHO)
    assert decision.status in ("failed", "blocked")
    pad.plug_in()
    await driver.connect()
    assert (await driver.health()).connected
    assert pad.writes == []


async def test_identify_discover_and_describe() -> None:
    driver, pad = make()
    assert await driver.identify() == {"name": "auto", "usb": "1209:4d48"}
    assert await driver.describe() is None
    await driver.connect()
    identity = await driver.identify()
    assert identity == {
        "usb": "1209:4d48",
        "manufacturer": "OpenHAL Labs",
        "product": "Sim Macropad",
        "serial": "MP-0001",
    }
    described = await driver.describe()
    assert described is not None
    assert described["match"] == {"usb": ["1209:4d48"], "usb_class": "hid"}
    assert described["device"] == {"name": "Sim Macropad", "manufacturer": "OpenHAL Labs"}
    assert "dial" in described["read"]
    found = await HidDriver.discover(hid_module=FakeHid(pad))
    assert found[0].identifiers == {"usb": "1209:4d48", "usb_class": "hid", "serial_number": "MP-0001"}
    assert found[0].label == "OpenHAL Labs Sim Macropad"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    HidDriver(report.file)
