"""The ble driver against the fake BleakClient and the simulated room sensor."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.ble import codec
from openhal.drivers.ble.conformance import FILE
from openhal.drivers.ble.driver import BleDriver, normalize_uuid, short_uuid
from openhal.drivers.ble.simulator import (
    LED_CHAR,
    MODE_CHAR,
    SECRET_CHAR,
    FakePeripheral,
    FakeScanner,
    client_factory,
    uuid16,
)
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "ble" / "examples"
WHO = human("tester")
ADDRESS = "C0:FF:EE:00:00:01"


def make(file: DeviceFile = FILE, peripheral: FakePeripheral | None = None, *others: FakePeripheral) -> BleDriver:
    peripheral = peripheral or FakePeripheral()
    return BleDriver(file, client_factory=client_factory(peripheral), scanner=FakeScanner(peripheral, *others))


def device(channels: str, connect: str = f'{{ ble: "{ADDRESS}", timeout: 0.3 s }}', match: str = "") -> DeviceFile:
    return loads(
        f"device: T\nid: t\n{match}connect: {connect}\n{channels}\nhazard: low\n"
        "confirmed: { by: t, at: 2026-10-24 }\n"
    )


def auto(channels: str, match: str) -> DeviceFile:
    return device(channels, connect="{ ble: auto }", match=f"match: {match}\n")


async def kernel_for(driver: BleDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


# ---------------------------------------------------------------------- uuids and codec


def test_uuids() -> None:
    assert normalize_uuid("2A6E") == "00002a6e-0000-1000-8000-00805f9b34fb"
    assert normalize_uuid("0x2a19") == uuid16("2a19")
    assert normalize_uuid("1234abcd") == "1234abcd-0000-1000-8000-00805f9b34fb"
    assert normalize_uuid(LED_CHAR.upper()) == LED_CHAR
    assert short_uuid(uuid16("181a")) == "181a"
    assert short_uuid(LED_CHAR) == LED_CHAR
    with pytest.raises(ValueError, match="not a BLE UUID"):
        normalize_uuid("temperature")


@pytest.mark.parametrize(
    ("fmt", "data", "value"),
    [
        ("uint8", b"\xff", 255.0),
        ("sint8", b"\xff", -1.0),
        ("uint16", b"\x34\x12", 0x1234),
        ("sint16", struct.pack("<h", -2250), -2250.0),
        ("uint24", b"\x01\x00\x01", 65537.0),
        ("sint24", b"\xff\xff\xff", -1.0),
        ("uint32", struct.pack("<I", 1013250), 1013250.0),
        ("sint32", struct.pack("<i", -5), -5.0),
        ("float32", struct.pack("<f", 1.5), 1.5),
        ("float64", struct.pack("<d", -2.25), -2.25),
        ("sfloat", (0xF000 | 365).to_bytes(2, "little"), 36.5),
        ("float", ((0xFE << 24) | 3650).to_bytes(4, "little"), 36.5),
        ("utf8", b"ENV-1\x00", "ENV-1"),
    ],
)
def test_codec_round_trips(fmt: Any, data: bytes, value: float | str) -> None:
    decoded = codec.decode(data, fmt)
    assert decoded == pytest.approx(value) if isinstance(value, float) else decoded == value
    if fmt not in ("sfloat", "float", "utf8"):
        assert codec.encode(value, fmt) == data
    assert codec.decode(codec.encode(value, fmt), fmt) == pytest.approx(value) if isinstance(value, float) else True


@pytest.mark.parametrize(
    ("fmt", "data", "message"),
    [
        ("sfloat", (0x07FF).to_bytes(2, "little"), "NaN"),
        ("sfloat", (0x0802).to_bytes(2, "little"), "-INF"),
        ("float", (0x00800000).to_bytes(4, "little"), "NRes"),
        ("float32", struct.pack("<f", float("nan")), "finite"),
        ("uint16", b"\x01", "needs 2 bytes"),
    ],
)
def test_codec_refuses_invalid_values(fmt: Any, data: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        codec.decode(data, fmt)


def test_codec_offsets_byte_order_and_encode_limits() -> None:
    assert codec.decode(b"\x00\x12\x34", "uint16", start=1, order="big") == 0x1234
    with pytest.raises(ValueError, match="doesn't fit"):
        codec.encode(256, "uint8")
    with pytest.raises(ValueError, match="doesn't fit"):
        codec.encode(-129, "sint8")
    with pytest.raises(ValueError, match="too large"):
        codec.encode(1e300, "float32")
    with pytest.raises(ValueError, match="exactly"):
        codec.encode(1 / 3, "sfloat")


# ---------------------------------------------------------------------- maps


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { unit: W }", "needs a map"),
        ("read:\n  x: { unit: W, map: { characteristic: nope } }", "not a BLE UUID"),
        ("read:\n  x: { unit: W, map: { characteristic: 2a6e, format: sint12 } }", "uint8"),
        ("read:\n  x: { unit: W, map: { characteristic: 2a6e, scale: 0 } }", "zero"),
        ("read:\n  x: { type: string, map: { characteristic: 2a29 } }", "format: utf8"),
        ("read:\n  x: { unit: W, map: { characteristic: 2a29, format: utf8 } }", "can't be utf8"),
        ("read:\n  x: { type: image, map: { characteristic: 2a29 } }", "image"),
        ("read:\n  x: { type: enum, values: [a], map: { characteristic: 2a29 } }", "values for a"),
        ("write:\n  x: { unit: W, min: 0, max: 1, map: { characteristic: 2a29, byte: 1 } }", "only works for reads"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        BleDriver(loads(f"device: T\nconnect: {{ ble: auto }}\n{channels}\n"))


# ---------------------------------------------------------------------- reads


async def test_reads_streams_and_plain_characteristics() -> None:
    peripheral = FakePeripheral()
    driver = make(FILE, peripheral)
    await driver.connect()
    temperature = await driver.read("temperature")
    assert temperature.value == pytest.approx(22.5)
    assert temperature.unit == "degC"
    assert (await driver.read("pressure")).value == pytest.approx(1013.25)
    assert (await driver.read("battery")).value == 87.0
    assert (await driver.read("maker")).value == "OpenHAL Labs"
    peripheral.notify(uuid16("2a6e"), struct.pack("<h", 2875))
    assert (await driver.read("temperature")).value == pytest.approx(28.75)
    peripheral.temperature_c = 30.0
    peripheral.refresh()
    assert (await driver.read("temperature")).value == pytest.approx(28.75), "streams use the notified value"
    assert (await driver.read("led")).value == 0.0
    assert (await driver.read("mode")).value == "quiet"
    await driver.close()


async def test_byte_offsets_range_and_bool() -> None:
    channels = (
        "read:\n"
        "  high_byte: { unit: dimensionless, range: [0, 5], map: { characteristic: 2a6f, byte: 1 } }\n"
        "  charged: { type: bool, map: { characteristic: 2a19, off: 0 } }"
    )
    peripheral = FakePeripheral()
    driver = make(device(channels), peripheral)
    await driver.connect()
    reading = await driver.read("high_byte")
    assert reading.value == float(4000 >> 8)
    assert reading.suspect is True
    assert (await driver.read("charged")).value is True


async def test_short_values_and_failures_raise() -> None:
    peripheral = FakePeripheral()
    driver = make(device("read:\n  t: { unit: degC, map: { characteristic: 2a6e, format: uint32 } }"), peripheral)
    await driver.connect()
    with pytest.raises(DriverError, match="needs 4 bytes"):
        await driver.read("t")
    peripheral.fail_reads = True
    with pytest.raises(DriverError, match="Read failed"):
        await driver.read("t")
    peripheral.fail_reads = False
    peripheral.delay_s = 1.0
    with pytest.raises(TimeoutError, match="didn't answer"):
        await driver.read("t")


async def test_missing_characteristics() -> None:
    channels = "read:\n  ghost: { unit: W, stream: true, map: { characteristic: 2a99 } }"
    with pytest.raises(DriverError, match="no characteristic"):
        await make(device(channels)).connect()
    channels = "read:\n  ghost: { unit: W, map: { characteristic: 2a99 } }"
    driver = make(device(channels))
    await driver.connect()
    with pytest.raises(DriverError, match="no characteristic"):
        await driver.read("ghost")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


async def test_write_only_characteristic_reports_last_written_value() -> None:
    channels = f"write:\n  secret: {{ unit: dimensionless, min: 0, max: 10, map: {{ characteristic: {SECRET_CHAR} }} }}"
    peripheral = FakePeripheral()
    driver = make(device(channels), peripheral)
    kernel = await kernel_for(driver)
    assert (await driver.read("secret")).value is None
    decision = await kernel.execute(Write(device="t", channel="secret", value="7 dimensionless"), WHO)
    assert decision.status == "done", decision.message
    assert (await driver.read("secret")).value == 7.0


# ---------------------------------------------------------------------- writes


async def test_writes_through_the_kernel() -> None:
    peripheral = FakePeripheral()
    driver = make(FILE, peripheral)
    kernel = await kernel_for(driver)
    for channel, value in (("led", "40 %"), ("mode", "fast")):
        decision = await kernel.execute(Write(device="conformance-ble", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert (LED_CHAR, bytes([80]), False) in peripheral.writes
    assert (MODE_CHAR, bytes([2]), False) in peripheral.writes
    assert (await driver.read("led")).value == pytest.approx(40.0)
    assert (await driver.read("mode")).value == "fast"


async def test_write_failures() -> None:
    channels = (
        "write:\n"
        f"  big: {{ unit: percent, min: 0, max: 100, map: {{ characteristic: {LED_CHAR}, scale: 0.1 }} }}\n"
        f"  strict: {{ type: bool, map: {{ characteristic: {MODE_CHAR}, response: true }} }}\n"
        "  label: { type: string, max_length: 8, map: { characteristic: 2a29, format: utf8 } }"
    )
    peripheral = FakePeripheral()
    driver = make(device(channels), peripheral)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="big", value="100 %"), WHO)
    assert decision.status == "failed"
    assert "doesn't fit in uint8" in decision.message
    decision = await kernel.execute(Write(device="t", channel="strict", value=True), WHO)
    assert decision.status == "failed"
    assert "Write not permitted" in decision.message
    decision = await kernel.execute(Write(device="t", channel="label", value="hello"), WHO)
    assert decision.status == "failed"
    assert peripheral.writes == []


# ---------------------------------------------------------------------- connection


async def test_auto_address_needs_exactly_one_match() -> None:
    first = FakePeripheral()
    second = FakePeripheral(address="C0:FF:EE:00:00:02", name="ENV-lab")
    channels = "read:\n  t: { unit: degC, map: { characteristic: 2a6e, format: sint16, scale: 0.01 } }"
    with pytest.raises(DriverError, match=r"needs match\.ble_name"):
        await make(device(channels, connect="{ ble: auto }"), first).connect()
    with pytest.raises(DriverError, match="2 advertising devices matched"):
        await make(
            device(channels, connect="{ ble: auto }", match='match: { ble_name: "^ENV-" }\n'), first, second
        ).connect()
    with pytest.raises(DriverError, match="0 advertising devices"):
        await make(auto(channels, '{ ble_name: "^NOPE" }'), first).connect()
    driver = make(
        device(channels, connect="{ ble: auto }", match='match: { ble_name: "desk$", ble_services: ["181a"] }\n'),
        first,
        second,
    )
    await driver.connect()
    assert (await driver.identify())["address"] == first.address


async def test_connect_failures() -> None:
    channels = "read:\n  t: { unit: degC, map: { characteristic: 2a6e, format: sint16, scale: 0.01 } }"
    peripheral = FakePeripheral(refuse_connect=True)
    driver = make(device(channels), peripheral)
    with pytest.raises(DriverError, match="advertising, in range"):
        await driver.connect()
    assert (await driver.health()).connected is False
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("t")
    slow = FakePeripheral(delay_s=2.0)
    with pytest.raises(TimeoutError, match="did not connect"):
        await make(device(channels), slow).connect()


async def test_dropped_link_and_reconnect() -> None:
    peripheral = FakePeripheral()
    driver = make(FILE, peripheral)
    await driver.connect()
    assert (await driver.health()).connected
    peripheral.drop()
    health = await driver.health()
    assert health.connected is False
    assert "link dropped" in health.detail
    await driver.connect()
    assert peripheral.connections == 2
    peripheral.notify(uuid16("2a6f"), struct.pack("<H", 5500))
    assert (await driver.read("humidity")).value == pytest.approx(55.0)


# ---------------------------------------------------------------------- identify, describe, discover


async def test_identify_and_describe() -> None:
    driver = make(FILE)
    assert await driver.describe() is None
    await driver.connect()
    identity = await driver.identify()
    assert identity["manufacturer"] == "OpenHAL Labs"
    assert identity["model"] == "ENV-1"
    assert identity["firmware"] == "3.2.0"
    described = await driver.describe()
    assert described is not None
    assert described["device"] == {"name": "ENV-1", "manufacturer": "OpenHAL Labs", "model": "ENV-1"}
    assert described["match"] == {"ble_services": ["181a", "180f", "180a", "6e400001-b5a3-f393-e0a9-e50e24dcca9e"]}
    reads = described["read"]
    assert reads["temperature"] == {
        "unit": "degC",
        "map": {"characteristic": "2a6e", "format": "sint16", "scale": 0.01},
        "stream": True,
    }
    assert "stream" not in reads["pressure"]
    assert reads["battery_level"]["unit"] == "percent"
    assert LED_CHAR in described["notes"]
    file = DeviceFile.model_validate({"device": described["device"], "connect": {"ble": ADDRESS}, "read": reads})
    BleDriver(file)


async def test_discover_lists_advertisers() -> None:
    found = await BleDriver.discover(scanner=FakeScanner(FakePeripheral()), listen_s=0.1)
    assert len(found) == 1
    assert found[0].address == ADDRESS
    assert found[0].identifiers == {"ble_services": "181a", "ble_name": "ENV-desk"}


# ---------------------------------------------------------------------- examples


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    BleDriver(report.file)
