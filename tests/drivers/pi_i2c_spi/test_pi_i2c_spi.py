"""The pi-i2c-spi driver, against fake smbus2 and spidev buses with simulated chips."""

from __future__ import annotations

import errno
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.pi_i2c_spi import driver as module
from openhal.drivers.pi_i2c_spi.conformance import device_file
from openhal.drivers.pi_i2c_spi.driver import PiBusDriver, open_spi, parse_bus
from openhal.drivers.pi_i2c_spi.simulator import FakeI2CBus, FakeSpiBus, Mcp3008, Mcp4921, Tmp102
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "pi_i2c_spi" / "examples"
WHO = human("tester")
ADC = "{ command: [0x01, 0x90, 0x00], byte: 1, length: 2, bits: 10, scale: 0.0032258064516129 }"


@dataclass
class Memory:
    """A chip with 16-bit register addresses, such as a 24C32 EEPROM."""

    cells: bytearray = field(default_factory=lambda: bytearray(range(256)) * 16)
    pointer: int = 0

    def write(self, data: bytes) -> None:
        self.pointer = int.from_bytes(data[:2], "big")
        for index, value in enumerate(data[2:]):
            self.cells[self.pointer + index] = value

    def read(self, length: int) -> bytes:
        return bytes(self.cells[self.pointer : self.pointer + length])


@pytest.fixture
def chip() -> Tmp102:
    return Tmp102()


@pytest.fixture
def i2c(chip: Tmp102) -> FakeI2CBus:
    return FakeI2CBus(chips={0x48: chip})


@pytest.fixture
def spi() -> FakeSpiBus:
    return FakeSpiBus(chips={(0, 0): Mcp4921(), (0, 1): Mcp3008()})


def bare(channels: str, connect: str = "{ pi-i2c-spi: 1, address: 0x48 }") -> DeviceFile:
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


async def connected(file: DeviceFile, **kwargs: Any) -> PiBusDriver:
    driver = PiBusDriver(file, **kwargs)
    await driver.connect()
    return driver


async def kernel_for(driver: PiBusDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


@pytest.mark.parametrize(
    ("text", "expected"),
    [(1, ("i2c", 1, 0)), ("i2c-1", ("i2c", 1, 0)), ("/dev/i2c-20", ("i2c", 20, 0)), ("3", ("i2c", 3, 0))],
)
def test_i2c_bus_names(text: Any, expected: tuple[str, int, int]) -> None:
    assert parse_bus(text) == expected


@pytest.mark.parametrize("text", ["spi0.1", "/dev/spidev1.2", "spidev0.0"])
def test_spi_bus_names(text: str) -> None:
    kind, _, _ = parse_bus(text)
    assert kind == "spi"


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ pi-i2c-spi: 1 }", "need address"),
        ("{ pi-i2c-spi: spi0.0, address: 0x48 }", "remove address"),
        ("{ pi-i2c-spi: usb0, address: 0x48 }", "not an I2C bus"),
        ("{ pi-i2c-spi: 1, address: 0x80 }", "less than or equal"),
        ("{ pi-i2c-spi: spi0.0, mode: 4 }", "Input should be"),
        ("{ pi-i2c-spi: 1, address: 0x48, colour: red }", "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        PiBusDriver(bare("read:\n  x: { unit: V, map: { register: 0 } }", connect))


@pytest.mark.parametrize(
    ("channels", "connect", "message"),
    [
        ("read:\n  x: { unit: V }", None, "needs a map"),
        ("read:\n  x: { unit: V, map: { register: 0, command: [1] } }", None, "command bytes are for SPI"),
        ("read:\n  x: { unit: V, map: { register: 0x100 } }", None, "wider than register_width"),
        ("read:\n  x: { unit: V, map: { register: 0, read_length: 65 } }", None, "less than or equal to 64"),
        ("read:\n  x: { unit: V, map: { command: [1], register: 1 } }", "{ pi-i2c-spi: spi0.0 }", "not register"),
        ("read:\n  x: { unit: V, map: { byte: 1 } }", "{ pi-i2c-spi: spi0.0 }", "SPI reads need command"),
        ("write:\n  x: { type: bool, map: { bit: 1, bits: 1 } }", None, "needs register"),
        ("write:\n  x: { type: bool, map: { preserve: true, data: [0] } }", "{ pi-i2c-spi: spi0.0 }", "preserve"),
        ("actions:\n  go: { map: { data: [1] } }", None, "needs register"),
        ("actions:\n  go: { args: { n: { unit: V, min: 0, max: 1 } }, map: { register: 1 } }", None, "every argument"),
        ("actions:\n  go: { map: {} }", "{ pi-i2c-spi: spi0.0 }", "needs data"),
        ("read:\n  x: { type: string, map: { register: 0 } }", None, "string channel"),
    ],
)
def test_bad_maps(channels: str, connect: str | None, message: str) -> None:
    file = bare(channels, connect) if connect else bare(channels)
    with pytest.raises(DriverError, match=message):
        PiBusDriver(file)


async def test_reads_decode_left_justified_twos_complement(i2c: FakeI2CBus, chip: Tmp102) -> None:
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    reading = await driver.read("temperature")
    assert reading.value == 23.5
    assert reading.unit == "degC"
    chip.temperature = -10.25
    assert (await driver.read("temperature")).value == -10.25
    chip.temperature = 127.0
    hot = await driver.read("temperature")
    assert hot.value == 127.0
    assert hot.suspect
    assert i2c.log[0] == ("read", 0x48, bytes([0x00, 0x17, 0x80]))
    assert (await driver.read("alert_high")).value == 80.0
    assert (await driver.read("shutdown")).value is False
    assert (await driver.read("rate")).value == "4 Hz"
    await driver.close()


async def test_writes_go_through_the_kernel_to_listed_registers(i2c: FakeI2CBus, chip: Tmp102) -> None:
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-tmp102", channel="alert_high", value="60.1 degC"), WHO)
    assert decision.status == "done", decision.message
    assert chip.t_high == 60.125
    assert i2c.writes(0x48)[-1] == bytes([0x03, 0x3C, 0x20])
    assert (await driver.read("alert_high")).value == 60.125
    await driver.close()


async def test_preserve_changes_only_the_field_bits(i2c: FakeI2CBus, chip: Tmp102) -> None:
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-tmp102", channel="shutdown", value=True), WHO)
    assert decision.status == "done", decision.message
    assert chip.config == 0x61A0
    assert i2c.writes(0x48)[-1] == bytes([0x01, 0x61, 0xA0])
    decision = await kernel.execute(Write(device="conformance-tmp102", channel="rate", value="1 Hz"), WHO)
    assert decision.status == "done", decision.message
    assert chip.config == 0x6160
    assert chip.shut_down
    assert (await driver.read("rate")).value == "1 Hz"
    assert (await driver.read("shutdown")).value is True
    await driver.close()


async def test_write_without_state_reads_back_the_value_sent(i2c: FakeI2CBus, chip: Tmp102) -> None:
    file = bare(
        "write:\n  low: { unit: degC, min: -40, max: 125, map: { register: 2, length: 2, bit: 4, bits: 12, "
        "signed: true, scale: 0.0625 } }"
    )
    driver = await connected(file, i2c_factory=i2c.i2c)
    assert (await driver.read("low")).value is None
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="low", value="-5 degC"), WHO)
    assert decision.status == "done", decision.message
    assert chip.t_low == -5.0
    assert (await driver.read("low")).value == -5.0
    await driver.close()


async def test_actions_place_arguments_in_listed_registers(i2c: FakeI2CBus, chip: Tmp102) -> None:
    file = bare(
        "actions:\n  set_low:\n    args: { low: { unit: degC, min: -40, max: 125 } }\n"
        "    map: { register: 2, data: [0, 0], args: { low: { length: 2, bit: 4, bits: 12, signed: true, "
        "scale: 0.0625 } } }"
    )
    driver = await connected(file, i2c_factory=i2c.i2c)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Action(device="t", action="set_low", args={"low": "21.5 degC"}), WHO)
    assert decision.status == "done", decision.message
    assert chip.t_low == 21.5
    assert i2c.writes(0x48)[-1] == bytes([0x02, 0x15, 0x80])
    await driver.close()


async def test_sixteen_bit_registers_and_plain_reads_use_i2c_rdwr() -> None:
    memory = Memory()
    bus = FakeI2CBus(chips={0x50: memory})
    file = bare(
        "read:\n  cell: { unit: dimensionless, map: { register: 0x0102, length: 2 } }\n"
        "  stream: { unit: dimensionless, map: { read_length: 40, byte: 39 } }\n"
        "write:\n  word: { unit: dimensionless, min: 0, max: 65535, map: { register: 0x0200, length: 2 } }",
        "{ pi-i2c-spi: 1, address: 0x50, register_width: 2 }",
    )
    driver = await connected(file, i2c_factory=bus.i2c)
    assert (await driver.read("cell")).value == float(0x0203)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="word", value="4660 dimensionless"), WHO)
    assert decision.status == "done", decision.message
    assert memory.cells[0x200:0x202] == b"\x12\x34"
    assert bus.log[-1] == ("rdwr-write", 0x50, b"\x02\x00\x12\x34")
    memory.pointer = 0x10
    assert (await driver.read("stream")).value == float(0x37)
    assert bus.log[-1][0] == "rdwr-read"
    await driver.close()


async def test_spi_reads_decode_the_reply_bytes(spi: FakeSpiBus) -> None:
    file = bare(f"read:\n  pot: {{ unit: V, map: {ADC} }}", "{ pi-i2c-spi: spi0.1, speed_hz: 1350000, mode: 0 }")
    driver = await connected(file, spi_factory=spi.spi)
    reading = await driver.read("pot")
    assert reading.value == pytest.approx(1.65, abs=0.005)
    target, sent, reply, speed, mode = spi.log[-1]
    assert (target, sent, speed, mode) == ((0, 1), bytes([0x01, 0x90, 0x00]), 1350000, 0)
    assert reply[1:] == bytes([0x02, 0x00])
    assert await driver.identify() == {"bus": "spi", "device": "spi0.1", "speed_hz": "1350000", "mode": "0"}
    await driver.close()


async def test_spi_writes_and_actions_clock_out_data(spi: FakeSpiBus) -> None:
    dac = spi.chips[(0, 0)]
    file = bare(
        "write:\n  output: { unit: V, min: 0, max: 3.3, map: { data: [0x30, 0x00], length: 2, bits: 12, "
        "scale: 0.0008056640625 } }\nactions:\n  power_down: { map: { data: [0x00, 0x00] } }",
        "{ pi-i2c-spi: spi0.0 }",
    )
    driver = await connected(file, spi_factory=spi.spi)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="output", value="1.2 V"), WHO)
    assert decision.status == "done", decision.message
    assert dac.word == 0x3000 | 1489
    assert dac.output == pytest.approx(1.2, abs=0.001)
    assert (await driver.read("output")).value == pytest.approx(1.2, abs=0.001)
    decision = await kernel.execute(Action(device="t", action="power_down"), WHO)
    assert decision.status == "done", decision.message
    assert dac.output == 0.0
    await driver.close()


async def test_a_missing_chip_is_reported_with_advice(i2c: FakeI2CBus) -> None:
    i2c.unplug(0x48)
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    with pytest.raises(DriverError, match="i2cdetect -y 1"):
        await driver.read("temperature")
    health = await driver.health()
    assert not health.connected
    assert "Nothing acknowledged" in health.detail
    await driver.close()


async def test_a_missing_bus_is_reported_with_advice(i2c: FakeI2CBus) -> None:
    driver = PiBusDriver(
        bare("read:\n  x: { unit: V, map: { register: 0 } }", "{ pi-i2c-spi: 3, address: 0x48 }"), i2c_factory=i2c.i2c
    )
    with pytest.raises(DriverError, match="/dev/i2c-3 doesn't exist"):
        await driver.connect()
    assert not (await driver.health()).connected


async def test_permission_problems_name_the_group() -> None:
    def refuse(number: int) -> Any:
        raise PermissionError(errno.EACCES, "Permission denied")

    driver = PiBusDriver(device_file(), i2c_factory=refuse)
    with pytest.raises(DriverError, match="i2c group"):
        await driver.connect()


async def test_other_failures_pass_the_error_on(i2c: FakeI2CBus, spi: FakeSpiBus) -> None:
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    i2c.closed = True
    with pytest.raises(DriverError, match="Bad file descriptor"):
        await driver.read("temperature")
    file = bare(f"read:\n  pot: {{ unit: V, map: {ADC} }}", "{ pi-i2c-spi: spi0.1 }")
    spi_driver = await connected(file, spi_factory=spi.spi)
    spi.fail_next = 1
    with pytest.raises(DriverError, match="Check the wiring and chip select"):
        await spi_driver.read("pot")
    missing = PiBusDriver(
        bare(f"read:\n  pot: {{ unit: V, map: {ADC} }}", "{ pi-i2c-spi: spi1.0 }"), spi_factory=spi.spi
    )
    with pytest.raises(DriverError, match=r"/dev/spidev1\.0 doesn.t exist"):
        await missing.connect()


async def test_slow_transactions_time_out(i2c: FakeI2CBus) -> None:
    driver = await connected(device_file(extra=", timeout: 100 ms"), i2c_factory=i2c.i2c)
    i2c.latency_s = 0.5
    with pytest.raises(TimeoutError, match="did not finish the read"):
        await driver.read("temperature")
    i2c.latency_s = 0.0
    await driver.close()


async def test_short_replies_fail_the_read(spi: FakeSpiBus) -> None:
    class Short:
        def transfer(self, data: bytes) -> bytes:
            return data[:1]

    spi.chips[(0, 1)] = Short()
    driver = await connected(
        bare(f"read:\n  pot: {{ unit: V, map: {ADC} }}", "{ pi-i2c-spi: spi0.1 }"), spi_factory=spi.spi
    )
    with pytest.raises(DriverError, match="returned 1 bytes, expected 3"):
        await driver.read("pot")


async def test_values_the_field_cannot_hold_are_not_written(i2c: FakeI2CBus) -> None:
    file = bare("write:\n  x: { unit: dimensionless, min: 0, max: 1000, map: { register: 2 } }")
    driver = await connected(file, i2c_factory=i2c.i2c)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="t", channel="x", value="300 dimensionless"), WHO)
    assert decision.status == "failed"
    assert "holds only 0 to 255" in decision.message
    assert i2c.writes(0x48) == []
    await driver.close()


async def test_closed_drivers_refuse_reads(i2c: FakeI2CBus) -> None:
    driver = await connected(device_file(), i2c_factory=i2c.i2c)
    await driver.close()
    await driver.close()
    with pytest.raises(DriverError, match="not open"):
        await driver.read("temperature")
    with pytest.raises(DriverError, match="not open"):
        await driver.read("alert_high")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("missing")


async def test_health_without_read_channels_reports_the_open_bus(spi: FakeSpiBus) -> None:
    file = bare(
        "write:\n  output: { unit: V, min: 0, max: 3.3, map: { data: [0x30, 0], length: 2, bits: 12 } }",
        "{ pi-i2c-spi: spi0.0 }",
    )
    driver = await connected(file, spi_factory=spi.spi)
    assert (await driver.health()).connected
    assert await driver.describe() is None
    await driver.close()


async def test_discover_lists_device_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    nodes = {"/dev/i2c-*": ["/dev/i2c-1", "/dev/i2c-20", "/dev/i2c-x"], "/dev/spidev*.*": ["/dev/spidev0.0"]}
    monkeypatch.setattr(module.glob, "glob", lambda pattern: nodes[pattern])
    found = await PiBusDriver.discover()
    assert [item.address for item in found] == ["i2c-1", "i2c-20", "spi0.0"]


def test_spidev_missing_gives_install_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "spidev", None)
    with pytest.raises(DriverError, match="installs only on Linux"):
        open_spi()


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable or not (report.file.write or report.file.actions)
    PiBusDriver(report.file)
