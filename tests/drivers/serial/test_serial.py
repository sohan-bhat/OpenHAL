"""The generic serial driver, against the simulated fan board and a real pty."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.serial import link as link_module
from openhal.drivers.serial.driver import SerialDriver
from openhal.drivers.serial.simulator import FanBoard, PtyBridge, SerialSimulator
from openhal.spec import loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

BOARD = r"""
device: Fan board
id: fan-board
connect: { serial: "sim://fan", timeout: 300 ms, identify: "ID?" }
read:
  temperature: { unit: degC, map: { query: "TEMP?", parse: "^T=(?P<value>-?[0-9.]+)$" } }
  temperature_f: { unit: degF, map: { query: "TEMP?", parse: "^T=([-0-9.]+)$", unit: degC } }
  board_id: { type: string, map: { query: "ID?" } }
write:
  fan_speed:
    unit: percent
    min: 0
    max: 100
    map:
      command: "FAN {value:.0f}"
      scale: 0.39215686
      expect: "^OK$"
      error: "^ERR"
      get: "FAN?"
      parse: "^FAN=(\\d+)$"
  led:
    type: bool
    map: { command: "LED {value}", on: "ON", off: "OFF", expect: "^OK$", get: "LED?", parse: "^LED=(ON|OFF)$" }
  mode:
    type: enum
    values: [quiet, normal, loud]
    map:
      command: "MODE {value}"
      lookup: { eco: quiet, normal: normal, boost: loud }
      error: "^ERR"
      get: "MODE?"
      parse: "^MODE=(\\w+)$"
  label: { type: string, max_length: 20, map: { command: "MODE {value}", error: "^ERR" } }
  raw_fan: { unit: dimensionless, min: 0, max: 400, map: { command: "FAN {value:.0f}", error: "^ERR" } }
actions:
  beep:
    args: { count: { unit: dimensionless, min: 1, max: 5, step: 1 } }
    map: { command: "BEEP {count:.0f}", expect: "^OK$" }
safe_state: { fan_speed: 0, led: false }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""

STREAM = r"""
device: Streaming board
id: stream-board
connect: { serial: "sim://fan", timeout: 300 ms }
read:
  temperature: { unit: degC, stream: true, map: { listen: "^T=(?P<value>-?[0-9.]+)$" } }
write:
  fan_speed:
    unit: percent
    min: 0
    max: 100
    map: { command: "FAN {value:.0f}", scale: 0.39215686, expect: "^OK$", get: "FAN?", parse: "^FAN=(\\d+)$" }
  led: { type: bool, map: { command: "LED {value}", on: "ON", off: "OFF" } }
safe_state: { fan_speed: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


def make(text: str = BOARD, board: FanBoard | None = None) -> tuple[SerialDriver, SerialSimulator, Bench]:
    sim = SerialSimulator(board or FanBoard())
    file = loads(text)
    driver = SerialDriver(file, opener=sim.opener)
    return driver, sim, Bench(file, driver)


async def test_reads_numbers_strings_and_converts_units() -> None:
    _, sim, bench = make()
    await bench.connect()
    reading = await bench.read("temperature")
    assert reading.value == pytest.approx(24.5)
    assert reading.unit == "degC"
    assert (await bench.read("temperature_f")).value == pytest.approx(76.1)
    assert (await bench.read("board_id")).value == "FANBOARD,1.2"
    assert "TEMP?\n" in sim.sent_text()
    await bench.close()


async def test_writes_scale_bool_and_enum_values() -> None:
    _, sim, bench = make()
    await bench.connect()
    assert_done(await bench.write("fan_speed", "50 %"))
    assert sim.model.fan == 128  # type: ignore[attr-defined]
    assert (await bench.read("fan_speed")).value == pytest.approx(50.196, abs=0.01)
    assert_done(await bench.write("led", True))
    assert "LED ON\n" in sim.sent_text()
    assert (await bench.read("led")).value is True
    assert_done(await bench.write("mode", "loud"))
    assert "MODE boost\n" in sim.sent_text()
    assert (await bench.read("mode")).value == "loud"
    await bench.close()


async def test_action_fills_its_template() -> None:
    _, sim, bench = make()
    await bench.connect()
    assert_done(await bench.act("beep", count="3 dimensionless"))
    assert sim.model.beeps == 3  # type: ignore[attr-defined]
    await bench.close()


async def test_error_reply_fails_the_write() -> None:
    _, _, bench = make()
    await bench.connect()
    assert_failed(await bench.write("raw_fan", "300 dimensionless"), "error reply")
    assert_failed(await bench.write("label", "turbo"), "ERR mode")
    await bench.close()


async def test_control_characters_never_reach_the_port() -> None:
    _, sim, bench = make()
    await bench.connect()
    before = len(sim.written)
    decision = await bench.write("label", "eco\nFAN 255")
    assert decision.status in ("blocked", "failed")
    assert len(sim.written) == before
    assert sim.model.fan == 0  # type: ignore[attr-defined]
    await bench.close()


async def test_identify_sends_the_configured_query() -> None:
    driver, _, bench = make()
    await bench.connect()
    assert await driver.identify() == {"port": "sim://fan", "reply": "FANBOARD,1.2"}
    await bench.close()


async def test_timeout_raises_and_late_replies_are_dropped() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.latency_s = 0.5
    with pytest.raises(TimeoutError, match="No reply to 'TEMP\\?'"):
        await driver.read("temperature")
    sim.latency_s = 0.0
    await eventually(lambda: _has_buffered(driver))
    reading = await driver.read("board_id")
    assert reading.value == "FANBOARD,1.2"
    await bench.close()


async def _has_buffered(driver: SerialDriver) -> bool:
    return not driver._replies.empty()


async def test_silent_device_times_out() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.silent = True
    with pytest.raises(TimeoutError):
        await driver.read("temperature")
    assert_failed(await bench.write("fan_speed", "10 %"), "No reply")
    await bench.close()


async def test_malformed_reply_raises() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.garble = True
    with pytest.raises(DriverError, match="doesn't match"):
        await driver.read("temperature")
    sim.garble = False
    board = FanBoard()
    board.answer = lambda line: "T=abc"  # type: ignore[method-assign]
    sim.model = board
    with pytest.raises(DriverError, match="doesn't match"):
        await driver.read("temperature")
    board.answer = lambda line: "LED=MAYBE"  # type: ignore[method-assign]
    with pytest.raises(DriverError, match="doesn't match"):
        await driver.read("led")
    board.answer = lambda line: "MODE=turbo"  # type: ignore[method-assign]
    with pytest.raises(DriverError, match="not one of"):
        await driver.read("mode")
    board.answer = lambda line: "WHAT"  # type: ignore[method-assign]
    assert_failed(await bench.write("fan_speed", "10 %"), "doesn't match")
    await bench.close()


async def test_disconnect_and_reconnect() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.unplug()
    await eventually(lambda: _disconnected(driver))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("temperature")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert sim.opened == 2
    assert (await bench.read("temperature")).value == pytest.approx(24.5)
    await bench.close()


async def _disconnected(driver: SerialDriver) -> bool:
    return not (await driver.health()).connected


async def test_disconnect_while_waiting_for_a_reply() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.silent = True

    async def unplug_soon() -> None:
        import asyncio

        await asyncio.sleep(0.05)
        sim.unplug()

    import asyncio

    task = asyncio.create_task(unplug_soon())
    with pytest.raises(DriverError, match="disconnected"):
        await driver.read("temperature")
    await task
    await bench.close()


async def test_open_failure_is_a_driver_error() -> None:
    _, sim, bench = make()
    sim.refuse_open = True
    with pytest.raises(DriverError, match="refuse_open"):
        await bench.connect()


async def test_safe_state_comes_from_the_file() -> None:
    _, sim, bench = make()
    await bench.connect()
    assert_done(await bench.write("fan_speed", "40 %"))
    assert_done(await bench.write("led", True))
    assert await bench.stop() == "safe"
    assert sim.model.fan == 0  # type: ignore[attr-defined]
    assert sim.model.led is False  # type: ignore[attr-defined]
    await bench.close()


async def test_stream_channels_take_unsolicited_lines() -> None:
    board = FanBoard(temperature=19.0)
    driver, sim, bench = make(STREAM, board)
    await bench.kernel.connect(bench.device)
    with pytest.raises(DriverError, match="has arrived"):
        await driver.read("temperature")
    sim.push(b"T=21.25\n")
    await eventually(lambda: _has_stream(driver))
    assert (await driver.read("temperature")).value == pytest.approx(21.25)
    board.stream = True
    assert_done(await bench.write("fan_speed", "20 %"))
    await eventually(lambda: _stream_is(driver, 19.0))
    assert driver.stream_age("temperature") is not None
    await bench.close()


async def _has_stream(driver: SerialDriver) -> bool:
    return "temperature" in driver._streamed


async def _stream_is(driver: SerialDriver, value: float) -> bool:
    reading = driver._streamed.get("temperature")
    return reading is not None and reading.value == pytest.approx(value)


async def test_write_channel_without_get_reports_the_last_sent_value() -> None:
    driver, _, bench = make(STREAM)
    await bench.connect()
    assert (await driver.read("led")).value is None
    assert_done(await bench.write("led", True))
    assert (await driver.read("led")).value is True
    await bench.close()


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { t: { unit: degC } }", "needs a map"),
        ("read: { t: { unit: degC, map: { query: 'A', listen: 'B' } } }", "exactly one of query or listen"),
        ("read: { t: { unit: degC, map: { query: 'A', parse: '(' } } }", "Invalid pattern"),
        ("read: { t: { unit: degC, map: { query: 'A', scale: 0 } } }", "scale"),
        ("read: { t: { unit: degC, map: { query: 'A', unit: parsec_per_banana } } }", "Unknown unit"),
        ("read: { t: { unit: degC, map: { query: 'A {value}' } } }", "not allowed"),
        ("read: { t: { type: image, map: { query: 'A' } } }", "images"),
        ("read: { t: { unit: degC, map: { query: 'A', extra: 1 } } }", "Extra inputs"),
        ("write: { w: { type: bool, map: { command: 'W {other}' } } }", "not allowed"),
        ("write: { w: { type: bool, map: { command: 'W {value!r}' } } }", "conversions"),
        ("write: { w: { type: bool, map: { command: 'W {value:d}' } } }", "could not fill"),
        ("write: { w: { type: bool, map: { command: 'W {' } } }", "not a valid template"),
        ("write: { w: { type: bool, map: { command: 'W {value}', get: 'G {value}' } } }", "not allowed"),
        ("actions: { a: { args: { n: { unit: s, min: 0, max: 1 } }, map: { command: 'A {m}' } } }", "not allowed"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"""
device: Bad
connect: {{ serial: /dev/null }}
{snippet}
"""
    with pytest.raises(DriverError, match=message):
        SerialDriver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("baud: 1", "greater than or equal"),
        ("newline: tab", "Input should be"),
        ("timeout: 5", "needs a unit"),
        ("timeout: 60 s", "between"),
        ("settle: 20 s", "between"),
        ("colour: blue", "Extra inputs"),
        ('identify: "ID?\\n"', "control characters"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    text = f"""
device: Bad
connect: {{ serial: /dev/null, {params} }}
read: {{ t: {{ unit: degC, map: {{ query: T }} }} }}
"""
    with pytest.raises(Exception, match=message):
        SerialDriver(loads(text))


def _ports(*items: dict[str, Any]) -> list[SimpleNamespace]:
    return [SimpleNamespace(**{"vid": None, "pid": None, "serial_number": None, **item}) for item in items]


def test_auto_port_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = _ports(
        {"device": "/dev/ttyACM0", "vid": 0x2341, "pid": 0x0043, "serial_number": "A1"},
        {"device": "/dev/ttyACM1", "vid": 0x2341, "pid": 0x0043, "serial_number": "B2"},
        {"device": "/dev/ttyUSB0", "vid": 0x1A86, "pid": 0x7523},
    )
    monkeypatch.setattr(link_module, "list_serial_ports", lambda: listed)
    resolve = link_module.resolve_port
    assert resolve("/dev/x", [], None, driver="serial") == "/dev/x"
    assert resolve("auto", ["1a86:7523"], None, driver="serial") == "/dev/ttyUSB0"
    assert resolve("auto", ["2341:0043"], "^B", driver="serial") == "/dev/ttyACM1"
    with pytest.raises(DriverError, match="Several ports"):
        resolve("auto", ["2341:0043"], None, driver="serial")
    with pytest.raises(DriverError, match="No serial port"):
        resolve("auto", ["dead:beef"], None, driver="serial")
    with pytest.raises(DriverError, match=r"needs match\.usb"):
        resolve("auto", [], None, driver="serial")


async def test_discover_lists_ports_without_opening_them(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = _ports(
        {"device": "/dev/ttyACM0", "vid": 0x2341, "pid": 0x0043, "serial_number": "A1", "description": "Uno"},
    )
    monkeypatch.setattr("openhal.drivers.serial.driver.list_serial_ports", lambda: listed)
    found = await SerialDriver.discover()
    assert found[0].address == "/dev/ttyACM0"
    assert found[0].identifiers["usb"] == "2341:0043"
    assert found[0].label == "Uno"


def test_real_port_listing_does_not_crash() -> None:
    assert isinstance(link_module.list_serial_ports(), list)


@pytest.mark.skipif(sys.platform == "win32", reason="pty needs POSIX")
async def test_real_pyserial_on_a_pty() -> None:
    bridge = PtyBridge(FanBoard())
    try:
        text = BOARD.replace('"sim://fan"', f'"{bridge.path}", baud: 115200')
        file = loads(text)
        driver = SerialDriver(file)
        bench = Bench(file, driver)
        await bench.connect()
        assert (await bench.read("temperature")).value == pytest.approx(24.5)
        assert_done(await bench.write("fan_speed", "100 %"))
        assert bridge.model.fan == 255  # type: ignore[attr-defined]
        assert (await driver.health()).connected
        await bench.close()
        assert not (await driver.health()).connected
    finally:
        bridge.close()


async def test_missing_port_fails_with_a_clear_message() -> None:
    file = loads(BOARD.replace('"sim://fan"', '"/dev/openhal-no-such-port"'))
    driver = SerialDriver(file)
    with pytest.raises(DriverError, match="Could not open"):
        await driver.connect()


async def test_failed_write_leaves_the_channel_unknown() -> None:
    driver, _, bench = make()
    await bench.connect()
    assert_done(await bench.write("raw_fan", "100 dimensionless"))
    assert (await driver.read("raw_fan")).value == 100.0
    assert_failed(await bench.write("raw_fan", "300 dimensionless"), "error reply")
    assert (await driver.read("raw_fan")).value is None
    await bench.close()
