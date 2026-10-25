"""The can driver, on python-can's virtual bus against the simulated motor drive."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import can
import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.can import bits
from openhal.drivers.can.conformance import device_file, fresh_channel
from openhal.drivers.can.driver import CanDriver, CanParams, notation
from openhal.drivers.can.simulator import MotorController
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "can" / "examples"
WHO = human("tester")


@pytest.fixture
def channel() -> str:
    return fresh_channel()


@pytest.fixture
def node(channel: str) -> Iterator[MotorController]:
    with MotorController(channel) as running:
        yield running


async def eventually(condition: Callable[[], Any], within: float = 2.0) -> None:
    deadline = time.monotonic() + within
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition did not become true in time")
        await asyncio.sleep(0.01)


async def connected(file: DeviceFile, **kwargs: Any) -> CanDriver:
    driver = CanDriver(file, **kwargs)
    await driver.connect()
    return driver


async def kernel_for(driver: CanDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = "{ can: vcan0, interface: virtual }") -> DeviceFile:
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


def test_field_extracts_bits_bytes_and_signs() -> None:
    data = bytes([0x12, 0x34, 0xFF, 0b0000_0110, 0x10, 0x27])
    assert bits.extract(data, bits.BitField(byte=0, length=2), "t") == 0x1234
    assert bits.extract(data, bits.BitField(byte=4, length=2, endian="little"), "t") == 10000
    assert bits.extract(data, bits.BitField(byte=2, signed=True), "t") == -1
    assert bits.extract(data, bits.BitField(byte=3, bit=1, bits=2), "t") == 3
    assert bits.extract(data, bits.BitField(byte=3, bit=0, bits=1), "t") == 0
    with pytest.raises(DriverError, match="too short"):
        bits.extract(data, bits.BitField(byte=5, length=2), "frame 0x101")


def test_field_insert_keeps_other_bits_and_refuses_values_it_cannot_hold() -> None:
    payload = bytearray([0xFF, 0x00])
    bits.insert(payload, bits.BitField(byte=0, bit=4, bits=2), 0, "t")
    assert payload == bytearray([0b1100_1111, 0x00])
    bits.insert(payload, bits.BitField(byte=1, signed=True), -2, "t")
    assert payload[1] == 0xFE
    grown = bytearray()
    bits.insert(grown, bits.BitField(byte=2, length=2, endian="little"), 0x0102, "t")
    assert grown == bytearray([0, 0, 0x02, 0x01])
    with pytest.raises(DriverError, match="holds only 0 to 255"):
        bits.insert(bytearray(1), bits.BitField(), 256, "write.x")
    with pytest.raises(DriverError, match="-128 to 127"):
        bits.insert(bytearray(1), bits.BitField(signed=True), 128, "write.x")


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ({"bit": 7, "bits": 2}, "don't fit"),
        ({"byte": 63, "length": 2}, "runs past"),
        ({"scale": 0}, "scale"),
        ({"unit": "zorkmids"}, "zorkmids"),
        ({"length": 9}, "less than or equal to 8"),
    ],
)
def test_bad_fields(field: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        bits.BitField.model_validate(field)


def test_to_raw_rounds_to_the_raw_step_and_converts_units() -> None:
    spec = loads("device: T\nconnect: { mock: x }\nwrite:\n  t: { unit: degC, min: 0, max: 100 }\n").write["t"]
    raw, sent = bits.to_raw(21.37, spec, bits.BitField(scale=0.5), "t")
    assert (raw, sent) == (43, 21.5)
    raw, sent = bits.to_raw(25.0, spec, bits.BitField(scale=0.1, unit="degF"), "t")
    assert raw == 770
    assert sent == pytest.approx(25.0, abs=0.06)


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ can: vcan0, interface: telepathy }", "Unknown python-can interface"),
        ("{ can: vcan0, interface: virtual, data_bitrate: 2000000 }", "fd: true"),
        ("{ can: vcan0, interface: virtual, bitrate: 10 }", "greater than or equal"),
        ("{ can: vcan0, interface: virtual, colour: red }", "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        CanDriver(bare("read:\n  x: { unit: rpm, map: { id: 1 } }", connect))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { unit: rpm }", "needs a map"),
        ("read:\n  x: { unit: rpm, map: { id: 0x800, extended: false } }", "29-bit"),
        ("read:\n  x: { unit: rpm, map: { id: 1, byte: 7, length: 2 } }", "at most 8"),
        ("read:\n  x: { unit: rpm, map: { id: 1, colour: red } }", "Extra inputs"),
        ("read:\n  x: { type: string, map: { id: 1 } }", "string channel"),
        ("read:\n  x: { type: enum, values: [a], map: { id: 1 } }", "needs map.lookup"),
        ("read:\n  x: { type: enum, values: [a], map: { id: 1, lookup: { 0: b } } }", "don't list"),
        ("read:\n  x: { unit: rpm, map: { id: 1, unit: V } }", "doesn't convert"),
        ("write:\n  x: { type: enum, values: [a, b], map: { id: 1, lookup: { 0: a } } }", "no raw value for b"),
        ("write:\n  x: { type: bool, map: { id: 1, data: [0, 0, 0, 0, 0, 0, 0, 0, 0] } }", "at most 8"),
        ("actions:\n  go: { args: { n: { unit: rpm, min: 0, max: 9 } }, map: { id: 1 } }", "every argument"),
        ("actions:\n  go: {}", "needs a map"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        CanDriver(bare(channels))


def test_fd_allows_longer_payloads() -> None:
    driver = CanDriver(bare("read:\n  x: { unit: rpm, map: { id: 1, byte: 20, length: 2 } }", "{ can: v, fd: true }"))
    assert driver.reads["x"].end == 22


async def test_reads_decode_the_newest_status_frame(channel: str, node: MotorController) -> None:
    node.voltage = 24.31
    driver = await connected(device_file(channel))
    await eventually(lambda: driver.reads["speed"].key in driver._latest)
    speed = await driver.read("speed")
    assert speed.value == 0.0
    assert speed.unit == "rpm"
    assert (await driver.read("motor_temp")).value == pytest.approx(24.0)
    assert (await driver.read("voltage")).value == pytest.approx(24.31)
    assert (await driver.read("enabled")).value is False
    assert (await driver.read("mode")).value == "coast"
    await driver.close()


async def test_a_frame_never_seen_reads_as_unknown(channel: str) -> None:
    driver = await connected(device_file(channel))
    reading = await driver.read("speed")
    assert reading.value is None
    assert reading.unit == "rpm"
    assert (await driver.read("setpoint")).value is None
    await driver.close()


async def test_out_of_range_readings_are_suspect(channel: str, node: MotorController) -> None:
    node.temperature = 150.0
    driver = await connected(device_file(channel))
    await asyncio.sleep(0.1)
    reading = await driver.read("motor_temp")
    assert reading.value == pytest.approx(150.0, abs=1.0)
    assert reading.suspect
    await driver.close()


async def test_a_short_frame_fails_the_read(channel: str, node: MotorController) -> None:
    node.malformed = True
    driver = await connected(device_file(channel))
    await asyncio.sleep(0.1)
    with pytest.raises(DriverError, match="too short"):
        await driver.read("voltage")
    await driver.close()


async def test_writes_share_one_command_frame(channel: str, node: MotorController) -> None:
    driver = await connected(device_file(channel))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-can", channel="setpoint", value="1500 rpm"), WHO)
    assert decision.status == "done", decision.message
    decision = await kernel.execute(Write(device="conformance-can", channel="enable", value=True), WHO)
    assert decision.status == "done", decision.message
    await eventually(lambda: len(node.frames(0x201)) == 2)
    assert node.frames(0x201) == [bytes([0x05, 0xDC, 0x00]), bytes([0x05, 0xDC, 0x01])]
    await eventually(lambda: node.speed == 1500.0)
    await asyncio.sleep(0.1)
    assert (await driver.read("speed")).value == 1500.0
    assert (await driver.read("enable")).value is True
    assert (await driver.read("setpoint")).value == 1500.0
    await driver.close()


async def test_enum_write_reads_back_from_the_status_frame(channel: str, node: MotorController) -> None:
    driver = await connected(device_file(channel))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-can", channel="mode", value="sport"), WHO)
    assert decision.status == "done", decision.message
    await eventually(lambda: node.mode == 2)
    await asyncio.sleep(0.1)
    assert (await driver.read("mode")).value == "sport"
    await driver.close()


async def test_actions_send_their_frame_with_arguments(channel: str, node: MotorController) -> None:
    node.fault = True
    driver = await connected(device_file(channel))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(
        Action(device="conformance-can", action="set_ramp", args={"rate": "500 rpm/s"}), WHO
    )
    assert decision.status == "done", decision.message
    decision = await kernel.execute(Action(device="conformance-can", action="clear_fault"), WHO)
    assert decision.status == "done", decision.message
    await eventually(lambda: not node.fault)
    assert node.ramp == 500.0
    assert node.frames(0x2FF) == [bytes([0x02, 0x01, 0xF4]), bytes([0x01])]
    await driver.close()


async def test_extended_ids_round_trip(channel: str) -> None:
    file = bare(
        "read:\n  x: { unit: rpm, map: { id: 0x18FF0001, length: 2 } }\n"
        "write:\n  y: { unit: rpm, min: 0, max: 9000, map: { id: 0x18FF0002, length: 2 } }",
        f"{{ can: {channel}, interface: virtual }}",
    )
    driver = await connected(file)
    peer = can.Bus(interface="virtual", channel=channel)
    try:
        peer.send(can.Message(arbitration_id=0x18FF0001, is_extended_id=True, data=b"\x00\x2a"))
        await eventually(lambda: driver.reads["x"].key in driver._latest)
        assert (await driver.read("x")).value == 42.0
        kernel = await kernel_for(driver)
        decision = await kernel.execute(Write(device="t", channel="y", value="7 rpm"), WHO)
        assert decision.status == "done", decision.message
        received = peer.recv(1.0)
        assert received is not None
        assert received.is_extended_id
        assert received.arbitration_id == 0x18FF0002
        assert bytes(received.data) == b"\x00\x07"
    finally:
        peer.shutdown()
        await driver.close()


async def test_fd_frames_are_padded_to_a_valid_length(channel: str) -> None:
    file = bare(
        "write:\n  y: { unit: rpm, min: 0, max: 9000, map: { id: 0x300, byte: 10, length: 2 } }",
        f"{{ can: {channel}, interface: virtual, fd: true }}",
    )
    driver = await connected(file)
    peer = can.Bus(interface="virtual", channel=channel)
    try:
        kernel = await kernel_for(driver)
        decision = await kernel.execute(Write(device="t", channel="y", value="258 rpm"), WHO)
        assert decision.status == "done", decision.message
        received = peer.recv(1.0)
        assert received is not None
        assert received.is_fd
        assert len(received.data) == 12
        assert bytes(received.data[10:12]) == b"\x01\x02"
    finally:
        peer.shutdown()
        await driver.close()


async def test_error_and_remote_frames_are_not_values(channel: str) -> None:
    driver = await connected(device_file(channel))
    peer = can.Bus(interface="virtual", channel=channel)
    try:
        peer.send(can.Message(arbitration_id=0x101, is_remote_frame=True, is_extended_id=False))
        peer.send(can.Message(arbitration_id=0x101, is_error_frame=True, is_extended_id=False))
        await eventually(lambda: driver.error_frames == 1)
        assert (await driver.read("speed")).value is None
    finally:
        peer.shutdown()
        await driver.close()


async def test_a_dropped_bus_is_reported_and_reconnects(channel: str, node: MotorController) -> None:
    driver = await connected(device_file(channel))
    assert (await driver.health()).connected
    assert driver.bus is not None
    driver.bus.shutdown()
    await eventually(lambda: driver._lost)
    health = await driver.health()
    assert not health.connected
    assert "failed" in health.detail
    with pytest.raises(DriverError, match="is down"):
        await driver.read("speed")
    kernel = await kernel_for(driver)
    await kernel.connect("conformance-can")
    await asyncio.sleep(0.1)
    assert (await driver.read("speed")).value == 0.0
    await driver.close()
    assert not (await driver.health()).connected
    with pytest.raises(DriverError, match="not open"):
        await driver.read("speed")


async def test_opening_a_missing_interface_fails_with_advice() -> None:
    def refuse(settings: CanParams) -> Any:
        raise can.CanInterfaceNotImplementedError("no such interface can9")

    driver = CanDriver(device_file("can9"), bus_factory=refuse)
    with pytest.raises(DriverError, match="ip link set can0 up"):
        await driver.connect()


async def test_a_bus_that_never_opens_times_out() -> None:
    def hang(settings: CanParams) -> Any:
        time.sleep(2.5)

    driver = CanDriver(device_file("slow", timeout="100 ms"), bus_factory=hang)
    with pytest.raises(TimeoutError, match="did not open"):
        await driver.connect()


class _RefusingBus:
    channel_info = "refusing bus"
    state = can.BusState.ACTIVE

    def __init__(self, error: Exception | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay

    def recv(self, timeout: float) -> None:
        time.sleep(timeout)

    def send(self, message: can.Message, timeout: float | None = None) -> None:
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error

    def shutdown(self) -> None:
        return None


async def test_a_refused_frame_fails_the_write() -> None:
    error = can.CanOperationError("Transmit buffer full")
    driver = await connected(device_file("x"), bus_factory=lambda settings: _RefusingBus(error))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-can", channel="setpoint", value="10 rpm"), WHO)
    assert decision.status == "failed"
    assert "Transmit buffer full" in decision.message
    assert (await driver.read("setpoint")).value is None
    assert "channel_info" in await driver.identify()
    await driver.close()


async def test_a_send_that_hangs_times_out() -> None:
    slow = _RefusingBus(delay=2)
    driver = await connected(device_file("x", timeout="100 ms"), bus_factory=lambda settings: slow)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-can", channel="enable", value=True), WHO)
    assert decision.status == "failed"
    assert "did not take frame" in decision.message
    await driver.close()


async def test_bus_off_reports_disconnected() -> None:
    bus_off = _RefusingBus()
    bus_off.state = can.BusState.ERROR
    driver = await connected(device_file("x"), bus_factory=lambda settings: bus_off)
    health = await driver.health()
    assert not health.connected
    assert "bus-off" in health.detail
    await driver.close()


async def test_describe_proposes_one_channel_per_frame(channel: str, node: MotorController) -> None:
    driver = await connected(device_file(channel))
    proposal = await driver.describe(listen_s=0.15)
    assert proposal is not None
    assert proposal["read"]["frame_101"] == {
        "unit": "dimensionless",
        "map": {"id": 0x101, "extended": False, "byte": 0, "length": 7},
    }
    assert "DBC" in proposal["notes"]
    await driver.close()
    assert await driver.describe() is None


async def test_discover_lists_socketcan_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        can, "detect_available_configs", lambda interfaces: [{"interface": "socketcan", "channel": "can0"}]
    )
    found = await CanDriver.discover()
    assert [item.address for item in found] == ["socketcan:can0"]

    def broken(interfaces: list[str]) -> list[dict[str, str]]:
        raise OSError("no ip command")

    monkeypatch.setattr(can, "detect_available_configs", broken)
    assert await CanDriver.discover() == []


async def test_identify_needs_no_bus() -> None:
    driver = CanDriver(device_file("vcan0", extra=", bitrate: 500000"))
    assert await driver.identify() == {"interface": "virtual", "channel": "vcan0", "bitrate": "500000"}


def test_notation_matches_candump() -> None:
    assert notation(0x201, False, b"\x05\xdc\x01") == "201#05DC01"
    assert notation(0x18FF0002, True, b"") == "18FF0002#"


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    assert report.file.connect.driver == "can"
    CanDriver(report.file)
