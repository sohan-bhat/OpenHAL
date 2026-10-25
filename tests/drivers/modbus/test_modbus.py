"""The modbus driver against pymodbus's own server running the simulated fan controller."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pymodbus.constants import ExcCodes

from openhal.conformance import run
from openhal.drivers.base import DriverError
from openhal.drivers.modbus import conformance
from openhal.drivers.modbus.driver import ModbusDriver, decode, encode
from openhal.drivers.modbus.simulator import ModbusSimulator
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "modbus" / "examples"
WHO = human("tester")


@pytest.fixture
def sim() -> Iterator[ModbusSimulator]:
    with ModbusSimulator("tcp") as simulator:
        yield simulator


def file_for(sim: ModbusSimulator, channels: str, *, connect_extra: str = "", timeout: str = "0.3 s") -> DeviceFile:
    connect = f"{{ modbus: tcp, host: 127.0.0.1, port: {sim.port}, timeout: {timeout}, retries: 0{connect_extra} }}"
    return loads(
        f"device: Test\nid: test\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


async def connected(file: DeviceFile) -> ModbusDriver:
    driver = ModbusDriver(file)
    await driver.connect()
    return driver


async def kernel_for(driver: ModbusDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(connect: str, channels: str = "read:\n  x: { unit: V, map: { register: 0 } }") -> DeviceFile:
    return loads(f"device: Test\nconnect: {connect}\n{channels}\n")


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ modbus: tcp }", "needs host"),
        ("{ modbus: tcp, host: h, port: /dev/ttyUSB0 }", "TCP port number"),
        ("{ modbus: tcp, host: h, port: 70000 }", "TCP port number"),
        ("{ modbus: rtu }", "needs port"),
        ("{ modbus: rtu, port: /dev/ttyUSB0, host: h }", "not host"),
        ("{ modbus: tcp, host: h, unit: 0 }", "greater than or equal to 1"),
        ("{ modbus: udp, host: h }", "'tcp' or 'rtu'"),
        ("{ modbus: tcp, host: h, timeout: 2 }", None),
    ],
)
def test_params(connect: str, message: str | None) -> None:
    if message is None:
        assert ModbusDriver(bare(connect)).settings.timeout == 2.0
        return
    with pytest.raises(ValueError, match=message):
        ModbusDriver(bare(connect))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { unit: V }", "needs a map"),
        ("read:\n  x: { unit: V, map: { register: -1 } }", "greater than or equal to 0"),
        ("read:\n  x: { unit: V, map: { register: 0, scale: 0 } }", "other than zero"),
        ("read:\n  x: { unit: V, map: { register: 0, format: float64 } }", "float32"),
        ("read:\n  x: { unit: V, map: { register: 65535, format: float32 } }", "past register 65535"),
        ("read:\n  x: { type: string, map: { register: 0 } }", "numbers, bools and enums"),
        ("read:\n  x: { unit: V, map: { register: 0, kind: coil } }", "must be type bool"),
        ("write:\n  x: { type: bool, map: { register: 0, kind: discrete } }", "read-only in Modbus"),
        ("write:\n  x: { unit: V, min: 0, max: 1, map: { register: 0, kind: input } }", "read-only in Modbus"),
        ("write:\n  x: { type: bool, map: { register: 0, bit: 3 } }", "read-only bool"),
        ("read:\n  x: { type: enum, values: [a, b], map: { register: 0, values: { a: 0 } } }", "values for b"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        ModbusDriver(bare("{ modbus: tcp, host: h }", channels))


@pytest.mark.parametrize(
    ("fmt", "value", "words", "byte_order"),
    [
        ("uint16", 513.0, [0x0201], "big"),
        ("int16", -2.0, [0xFFFE], "big"),
        ("uint32", 70000.0, [0x0001, 0x1170], "big"),
        ("int32", -70000.0, [0xFFFE, 0xEE90], "big"),
        ("float32", 230.5, [0x4366, 0x8000], "big"),
        ("uint16", 513.0, [0x0102], "little"),
    ],
)
def test_encode_and_decode_round_trip(fmt: Any, value: float, words: list[int], byte_order: Any) -> None:
    assert encode(value, fmt, "big", byte_order) == words
    assert decode(words, fmt, "big", byte_order) == value
    swapped = encode(value, fmt, "little", byte_order)
    assert swapped == list(reversed(words))
    assert decode(swapped, fmt, "little", byte_order) == value


@pytest.mark.parametrize(
    ("fmt", "value"), [("uint16", 70000.0), ("int16", 40000.0), ("uint32", -1.0), ("float32", 1e39)]
)
def test_encode_refuses_values_that_do_not_fit(fmt: Any, value: float) -> None:
    with pytest.raises(DriverError, match=r"fit|too large"):
        encode(value, fmt, "big", "big")


async def test_reads_every_table_and_format(sim: ModbusSimulator) -> None:
    driver = await connected(conformance.device_file(sim))
    assert (await driver.read("voltage")).value == pytest.approx(230.0)
    assert (await driver.read("power")).value == pytest.approx(2.5)
    temperature = await driver.read("motor_temperature")
    assert temperature.value == pytest.approx(24.5)
    assert temperature.unit == "degC"
    assert (await driver.read("door_closed")).value is True
    assert (await driver.read("run_hours")).value == 70000.0
    assert (await driver.read("enable")).value is False
    assert (await driver.read("mode")).value == "stop"
    sim.model.voltage = 190.0
    assert (await driver.read("voltage")).suspect is True
    await driver.close()


async def test_bits_bools_and_enums_on_registers(sim: ModbusSimulator) -> None:
    channels = (
        "read:\n"
        "  running: { type: bool, map: { register: 20, bit: 0 } }\n"
        "  not_stopped: { type: bool, map: { register: 20 } }\n"
        "  mode: { type: enum, values: [stop, run], map: { register: 20, values: { stop: 0, run: 1 } } }"
    )
    driver = await connected(file_for(sim, channels))
    assert (await driver.read("running")).value is False
    assert (await driver.read("not_stopped")).value is False
    sim.model.mode = 1
    assert (await driver.read("running")).value is True
    assert (await driver.read("mode")).value == "run"
    sim.model.mode = 2
    assert (await driver.read("not_stopped")).value is True
    with pytest.raises(DriverError, match="raw value 2"):
        await driver.read("mode")


async def test_nan_float_is_refused(sim: ModbusSimulator) -> None:
    driver = await connected(conformance.device_file(sim))
    sim.model.voltage = float("nan")
    with pytest.raises(DriverError, match="not a finite number"):
        await driver.read("voltage")


async def test_writes_reach_the_right_registers(sim: ModbusSimulator) -> None:
    driver = ModbusDriver(conformance.device_file(sim))
    kernel = await kernel_for(driver)
    for channel, value in (("speed", "42.5 %"), ("enable", True), ("mode", "auto")):
        decision = await kernel.execute(Write(device="conformance-modbus", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert (sim.model.speed_raw, sim.model.enable, sim.model.mode) == (425, True, 2)
    assert (5, 0, [True]) in sim.model.writes
    assert (6, 10, [425]) in sim.model.writes
    assert (await driver.read("speed")).value == pytest.approx(42.5)
    assert (await driver.read("power")).value == pytest.approx(2.5 + 0.45 * 425)
    await driver.close()


async def test_rounding_32_bit_writes_and_write_multiple(sim: ModbusSimulator) -> None:
    channels = (
        "write:\n"
        "  speed: { unit: percent, min: 0, max: 100, map: { register: 10, scale: 0.1 } }\n"
        "  target: { unit: V, min: -1000, max: 1000, map: { register: 30, format: float32, word_order: little } }\n"
        "  count: { unit: dimensionless, min: -100000, max: 100000, map: { register: 40, format: int32 } }\n"
        "  lamp: { type: bool, map: { register: 50, on: 255, off: 0 } }"
    )
    file = file_for(sim, channels, connect_extra=", always_write_multiple: true")
    driver = ModbusDriver(file)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="test", channel="speed", value="42.47 %"), WHO)
    assert decision.status == "done"
    assert sim.model.speed_raw == 425
    assert (16, 10, [425]) in sim.model.writes
    assert (await driver.read("speed")).value == pytest.approx(42.5)
    for channel, value, expected in (("target", "-12.25 V", -12.25), ("count", "-70000 dimensionless", -70000.0)):
        decision = await kernel.execute(Write(device="test", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
        assert (await driver.read(channel)).value == pytest.approx(expected)
    await kernel.execute(Write(device="test", channel="lamp", value=True), WHO)
    assert (16, 50, [255]) in sim.model.writes
    assert (await driver.read("lamp")).value is True


async def test_device_exceptions_fail_writes_and_reads(sim: ModbusSimulator) -> None:
    driver = ModbusDriver(conformance.device_file(sim))
    kernel = await kernel_for(driver)
    sim.exception = ExcCodes.ILLEGAL_VALUE
    decision = await kernel.execute(Write(device="conformance-modbus", channel="speed", value="10 %"), WHO)
    assert decision.status == "failed"
    assert "illegal data value" in decision.message
    sim.exception = ExcCodes.ILLEGAL_ADDRESS
    with pytest.raises(DriverError, match="illegal data address"):
        await driver.read("voltage")
    sim.exception = None
    channels = "read:\n  far: { unit: V, map: { register: 200, kind: input } }"
    other = await connected(file_for(sim, channels))
    with pytest.raises(DriverError, match="refused read_input_registers"):
        await other.read("far")


async def test_connect_fails_without_a_server() -> None:
    simulator = ModbusSimulator("tcp")
    driver = ModbusDriver(conformance.device_file(simulator))
    with pytest.raises(DriverError, match="Could not open"):
        await driver.connect()
    assert (await driver.health()).connected is False
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("voltage")


async def test_slow_device_times_out_and_turns_unhealthy(sim: ModbusSimulator) -> None:
    driver = await connected(
        file_for(sim, "read:\n  v: { unit: V, map: { register: 0, kind: input, format: float32 } }")
    )
    health = await driver.health()
    assert health.connected
    assert health.latency_ms is not None
    sim.delay_s = 1.5
    for _ in range(3):
        with pytest.raises(TimeoutError, match="didn't answer"):
            await driver.read("v")
    assert (await driver.health()).connected is False
    sim.delay_s = 0
    await driver.connect()
    assert (await driver.health()).connected is True


async def test_server_going_away_is_noticed(sim: ModbusSimulator) -> None:
    driver = await connected(conformance.device_file(sim))
    sim.stop()
    assert (await driver.health()).connected is False
    with pytest.raises((DriverError, TimeoutError)):
        await driver.read("voltage")
    sim.start()
    await driver.connect()
    assert (await driver.read("voltage")).value == pytest.approx(230.0)


async def test_identify_and_describe(sim: ModbusSimulator) -> None:
    driver = ModbusDriver(conformance.device_file(sim))
    identity = await driver.identify()
    assert identity == {"transport": "tcp", "unit": "1", "address": f"127.0.0.1:{sim.port}"}
    await driver.connect()
    assert (await driver.identify())["unit"] == "1"
    described = await driver.describe()
    assert described is not None
    assert described["match"] == {"modbus_id": 1}
    assert "manual" in described["notes"]
    assert await ModbusDriver.discover() == []


async def test_rtu_framing_passes_conformance() -> None:
    report = await run(conformance.case("rtu"))
    failures = [f"{result.name}: {result.detail}" for result in report.results if not result.ok and not result.skipped]
    assert report.ok, failures


async def test_rtu_reads_and_writes() -> None:
    with ModbusSimulator("rtu", unit=7) as simulator:
        driver = ModbusDriver(conformance.device_file(simulator))
        kernel = await kernel_for(driver)
        assert (await driver.read("voltage")).value == pytest.approx(230.0)
        decision = await kernel.execute(Write(device="conformance-modbus", channel="speed", value="5 %"), WHO)
        assert decision.status == "done"
        assert simulator.model.speed_raw == 50
        assert (await driver.identify())["address"].startswith("socket://")
        await driver.close()


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    ModbusDriver(report.file)
