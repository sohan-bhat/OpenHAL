"""The OpenHAL firmware protocol, its simulator and the driver, through the kernel."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from hypothesis import given
from hypothesis import strategies as st

from openhal.drivers.base import DriverError
from openhal.drivers.openhal_firmware import protocol
from openhal.drivers.openhal_firmware.driver import OpenHalFirmwareDriver
from openhal.drivers.openhal_firmware.simulator import SIMULATORS, FirmwareSimulator, SimTransport
from openhal.kernel import Kernel, Write, human
from openhal.spec import DeviceFile, loads

FAN = """
device: Bench fan
id: bench-fan
connect: { openhal-firmware: "sim:bench", timeout_s: 0.3 }
read:
  temperature: { unit: degC }
write:
  fan_speed: { unit: percent, min: 0, max: 100, max_change_per_s: 100 }
safe_state: { fan_speed: 0 }
confirmed: { by: tester, at: 2026-10-24 }
"""


@pytest.fixture
def file() -> DeviceFile:
    SIMULATORS.pop("bench", None)
    return loads(FAN)


@pytest.fixture
async def driver(file: DeviceFile) -> AsyncIterator[OpenHalFirmwareDriver]:
    device = OpenHalFirmwareDriver(file)
    await device.connect()
    yield device
    await device.close()
    SIMULATORS.pop("bench", None)


def test_checksum_matches_the_spec_example() -> None:
    assert (
        protocol.encode(7, "READ", "temperature")
        == "7 READ temperature*" + protocol.checksum("7 READ temperature") + "\n"
    )
    assert protocol.decode("7 READ temperature*" + protocol.checksum("7 READ temperature")).args == ("temperature",)


@pytest.mark.parametrize(
    "line",
    ["7 READ temperature", "7 READ temperature*00", "READ temperature*12", "x" * 300 + "*00", "*00"],
)
def test_malformed_lines_are_rejected(line: str) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.decode(line)


@given(
    seq=st.integers(0, 65535),
    verb=st.sampled_from(["READ", "WRITE", "VAL", "OK", "EVT"]),
    args=st.lists(st.from_regex(r"[a-z0-9_.+-]{1,12}", fullmatch=True), max_size=3),
)
def test_encode_decode_round_trip(seq: int, verb: str, args: list[str]) -> None:
    message = protocol.decode(protocol.encode(seq, verb, *args))
    assert (message.seq, message.verb, message.args) == (seq, verb, tuple(args))


@given(st.floats(-1e6, 1e6, allow_nan=False))
def test_numbers_round_trip_within_six_decimals(value: float) -> None:
    assert protocol.parse_number(protocol.format_number(value)) == pytest.approx(value, abs=1e-6)


@pytest.mark.parametrize("text", ["1e5", "nan", "inf", "", "0x10", "1,5"])
def test_only_plain_decimals_are_numbers(text: str) -> None:
    with pytest.raises(protocol.ProtocolError):
        protocol.parse_number(text)


def test_description_needs_numeric_limits_for_outputs() -> None:
    with pytest.raises(protocol.ProtocolError, match="numeric max"):
        protocol.parse_description('{"p":"x","w":[{"n":"led","u":"percent","min":0,"safe":0}]}')
    with pytest.raises(protocol.ProtocolError, match="valid name"):
        protocol.parse_description('{"p":"x","r":[{"n":"Bad Name","u":"degC"}]}')


def test_description_becomes_suggested_sections() -> None:
    sections = protocol.description_to_sections(FirmwareSimulator().description())
    assert sections["write"]["fan_speed"] == {
        "unit": "percent",
        "min": 0,
        "max": 100,
        "suggested": True,
        "max_change_per_s": 20,
    }
    assert sections["safe_state"] == {"fan_speed": 0}
    assert sections["watchdog"] == {"heartbeat": "1000 ms", "on_loss": "safe_state"}
    assert sections["match"] == {"firmware": {"product": "desk-fan"}}


async def _ask(sim: FirmwareSimulator, line: str) -> protocol.Message:
    sim.handle(line)
    return protocol.decode(await asyncio.wait_for(sim.to_host.get(), 1))


async def test_simulated_board_enforces_its_own_limits() -> None:
    sim = FirmwareSimulator()
    reply = await _ask(sim, protocol.encode(3, "WRITE", "fan_speed", "150"))
    assert (reply.verb, reply.args) == ("ERR", ("limit", "fan_speed", "max", "100"))
    assert sim.channels["fan_speed"].value == 0


async def test_simulated_board_falls_safe_without_heartbeats() -> None:
    sim = FirmwareSimulator(heartbeat_ms=50)
    await _ask(sim, protocol.encode(1, "WRITE", "fan_speed", "60"))
    await asyncio.sleep(0.08)
    sim.handle(protocol.encode(2, "READ", "fan_speed"))
    safe = protocol.decode(await sim.to_host.get())
    assert (safe.seq, safe.verb) == (0, "SAFE")
    value = protocol.decode(await sim.to_host.get())
    assert value.args == ("fan_speed", "0")


async def test_bad_checksum_gets_an_error_not_an_action() -> None:
    sim = FirmwareSimulator()
    reply = await _ask(sim, "1 WRITE fan_speed 60*00")
    assert reply.verb == "ERR"
    assert sim.channels["fan_speed"].value == 0


async def test_connect_identifies_and_describes(driver: OpenHalFirmwareDriver) -> None:
    assert await driver.identify() == {"protocol": "1", "product": "bench", "version": "1.0.0"}
    described = await driver.describe()
    assert described is not None
    assert described["write"]["fan_speed"]["suggested"] is True
    assert described["device"] == {"name": "Bench"}


async def test_reads_come_back_in_the_file_unit(driver: OpenHalFirmwareDriver) -> None:
    reading = await driver.read("temperature")
    assert reading.unit == "degC"
    assert isinstance(reading.value, float)


async def test_writes_need_a_kernel_grant(driver: OpenHalFirmwareDriver) -> None:
    with pytest.raises(PermissionError):
        await driver.write("fan_speed", 50.0, None)
    assert SIMULATORS["bench"].channels["fan_speed"].value == 0


async def _kernel(file: DeviceFile) -> tuple[Kernel, OpenHalFirmwareDriver]:
    """A kernel whose clock has moved on since connect, so the rate limit allows a full step."""
    now = [10_000.0]
    kernel = Kernel(clock=lambda: now[0])
    driver = OpenHalFirmwareDriver(file)
    kernel.register(file, driver)
    await kernel.connect("bench-fan")
    now[0] += 60
    return kernel, driver


async def test_kernel_write_reaches_the_board(file: DeviceFile) -> None:
    kernel, driver = await _kernel(file)
    decision = await kernel.execute(Write(device="bench-fan", channel="fan_speed", value="40 %"), human("tester"))
    assert decision.status == "done", decision.message
    assert SIMULATORS["bench"].channels["fan_speed"].value == 40
    blocked = await kernel.execute(Write(device="bench-fan", channel="fan_speed", value="150 %"), human("tester"))
    assert blocked.status == "blocked"
    assert SIMULATORS["bench"].channels["fan_speed"].value == 40
    await driver.close()


async def test_stop_sends_the_board_to_its_safe_state(file: DeviceFile) -> None:
    kernel, driver = await _kernel(file)
    moved = await kernel.execute(Write(device="bench-fan", channel="fan_speed", value="70 %"), human("tester"))
    assert moved.status == "done", moved.message
    result = await kernel.stop_all(human("tester"), "test")
    assert result.devices[0].status == "safe"
    assert SIMULATORS["bench"].channels["fan_speed"].value == 0
    assert any("SAFE" in line for line in SIMULATORS["bench"].received)
    await driver.close()


async def test_board_refusal_is_a_driver_error(driver: OpenHalFirmwareDriver) -> None:
    """The board's own limit is a second wall. Reaching it raises, it never passes silently."""
    SIMULATORS["bench"].channels["fan_speed"].maximum = 50
    with pytest.raises(DriverError, match="limit"):
        await driver._write("fan_speed", 80.0)


async def test_silent_board_times_out(driver: OpenHalFirmwareDriver) -> None:
    SIMULATORS["bench"].silent = True
    with pytest.raises(DriverError, match="didn't answer READ"):
        await driver.read("temperature")


async def test_corrupted_reply_is_discarded_and_times_out(driver: OpenHalFirmwareDriver) -> None:
    SIMULATORS["bench"].corrupt_next = True
    with pytest.raises(DriverError, match="didn't answer"):
        await driver.read("temperature")
    reading = await driver.read("temperature")
    assert reading.channel == "temperature"


async def test_heartbeats_keep_the_board_out_of_its_safe_state(file: DeviceFile) -> None:
    SIMULATORS["bench"] = FirmwareSimulator(product="bench", heartbeat_ms=150)
    driver = OpenHalFirmwareDriver(file)
    await driver.connect()
    await asyncio.sleep(0.5)
    assert SIMULATORS["bench"].safe_events == 0
    await driver.close()
    SIMULATORS.pop("bench", None)


async def test_streamed_events_answer_reads(driver: OpenHalFirmwareDriver) -> None:
    SIMULATORS["bench"].to_host.put_nowait(protocol.encode(0, "EVT", "temperature", "22.5"))
    await asyncio.sleep(0.01)
    SIMULATORS["bench"].silent = True
    reading = await driver.read("temperature")
    assert reading.value == 22.5


async def test_unplugged_board_reports_unhealthy(driver: OpenHalFirmwareDriver) -> None:
    link = driver._link
    assert link is not None
    await link.transport.close()
    health = await driver.health()
    assert not health.connected


async def test_a_non_openhal_board_is_refused(file: DeviceFile) -> None:
    class Stranger(SimTransport):
        async def write_line(self, line: str) -> None:
            message = protocol.decode(line)
            self.simulator.to_host.put_nowait(protocol.encode(message.seq, "OK", "marlin", "2"))

    driver = OpenHalFirmwareDriver(file)
    driver._make_transport = lambda: Stranger(FirmwareSimulator())  # type: ignore[method-assign]
    with pytest.raises(DriverError, match="OpenHAL library"):
        await driver.connect()
    await driver.close()
