"""The Firmata client, protocol parser and driver, against the simulated StandardFirmata board."""

from __future__ import annotations

import sys

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.firmata import protocol as p
from openhal.drivers.firmata.driver import FirmataDriver
from openhal.drivers.firmata.simulator import FirmataBoard
from openhal.drivers.serial.simulator import PtyBridge, SerialSimulator
from openhal.spec import loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

BOARD = """
device: Uno with Firmata
id: uno
connect: { firmata: "sim://uno", timeout: 300 ms, settle: 0 s, sampling: 20 ms, vref: 5 V }
read:
  light: { unit: V, map: { pin: A0 } }
  level: { unit: percent, map: { pin: A1 } }
  raw: { unit: dimensionless, map: { pin: 16 } }
  probe: { unit: degC, map: { pin: A3, scale: 0.1, offset: -20 } }
  button: { type: bool, map: { pin: 2, mode: pullup, invert: true } }
  door: { type: bool, map: { pin: 8 } }
write:
  led: { type: bool, map: { pin: 13 } }
  relay: { type: bool, map: { pin: 7, invert: true } }
  fan: { unit: percent, min: 0, max: 100, map: { pin: 9 } }
  arm: { unit: degree, min: 0, max: 180, map: { pin: 6, mode: servo, min_pulse: 600, max_pulse: 2300 } }
safe_state: { led: false, fan: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


def make(text: str = BOARD, board: FirmataBoard | None = None) -> tuple[FirmataDriver, FirmataBoard, Bench]:
    model = board or FirmataBoard()
    sim = SerialSimulator(model)
    file = loads(text)
    driver = FirmataDriver(file, opener=sim.opener)
    bench = Bench(file, driver)
    bench.sim = sim  # type: ignore[attr-defined]
    return driver, model, bench


async def _analog_ready(driver: FirmataDriver) -> bool:
    return len(driver.analog_values) >= 4


def test_seven_bit_helpers_round_trip() -> None:
    assert p.split14(1023) == (0x7F, 0x07)
    assert p.unpack7(p.pack7(0)) == 0
    assert p.unpack7(p.pack7(100_000)) == 100_000
    assert p.decode_string(p.encode_string("StandardFirmata.ino")) == "StandardFirmata.ino"
    assert p.sysex(p.REPORT_FIRMWARE) == bytes([0xF0, 0x79, 0xF7])


def test_parser_decodes_every_message_kind() -> None:
    parser = p.Parser()
    stream = bytes([0xE1, 0x7F, 0x07, 0x92, 0x05, 0x01, 0xF9, 2, 5]) + p.sysex(p.STRING_DATA, b"\x41\x00")
    messages = parser.feed(stream[:4]) + parser.feed(stream[4:])
    assert [m.kind for m in messages] == ["analog", "digital", "version", "sysex"]
    assert (messages[0].index, messages[0].value) == (1, 1023)
    assert (messages[1].index, messages[1].value) == (2, 0x85)
    assert (messages[2].index, messages[2].value) == (2, 5)
    assert messages[3].index == p.STRING_DATA


def test_parser_skips_malformed_bytes() -> None:
    parser = p.Parser()
    kinds = [m.kind for m in parser.feed(bytes([0x05, 0xF4, 0xF0, 0xF7, 0xF0, 0x79, 0x01, 0xE0, 0x01, 0x00]))]
    assert kinds == ["malformed", "malformed", "malformed", "malformed", "analog"]
    big = parser.feed(bytes([0xF0, 0x71]) + bytes(5000) + bytes([0xF7]))
    assert big[0].kind == "sysex"
    assert len(big[0].data) < p.MAX_SYSEX


def test_capabilities_parse() -> None:
    data = bytes([0, 1, 1, 1, 0x7F, 0x7F, 2, 10, 0x7F])
    assert p.parse_capabilities(data) == [{0: 1, 1: 1}, {}, {2: 10}]


async def test_connect_reads_firmware_and_configures_only_inputs() -> None:
    driver, board, bench = make()
    await bench.connect()
    identity = await driver.identify()
    assert identity == {
        "port": "sim://uno",
        "firmware": "StandardFirmata.ino",
        "firmware_version": "2.5",
        "protocol": "2.5",
    }
    assert board.modes[2] == p.PULLUP
    assert board.modes[8] == p.INPUT
    assert board.modes[13] == p.OUTPUT
    assert board.modes[9] == p.OUTPUT
    assert board.modes[6] == p.OUTPUT
    assert board.analog_reporting == {0, 1, 2, 3}
    assert board.digital_reporting == {0, 1}
    assert board.sampling_ms == 20
    assert bytes([p.SET_PIN_MODE, 13]) not in bytes(board.received)
    await bench.close()


async def test_analog_reads_convert_to_the_channel_unit() -> None:
    driver, board, bench = make()
    board.analog.update({0: 1023, 1: 512, 2: 300, 3: 400})
    await bench.connect()
    await eventually(lambda: _analog_ready(driver))
    assert (await bench.read("light")).value == pytest.approx(5.0)
    assert (await bench.read("level")).value == pytest.approx(50.05, abs=0.01)
    assert (await bench.read("raw")).value == 300
    assert (await bench.read("probe")).value == pytest.approx(20.0)
    await bench.close()


async def test_digital_inputs_follow_port_reports() -> None:
    driver, board, bench = make()
    await bench.connect()
    await eventually(lambda: _ports_ready(driver))
    assert (await bench.read("button")).value is True
    bench.sim.push(board.set_input(2, 1))  # type: ignore[attr-defined]
    await eventually(lambda: _button_is(driver, False))
    assert (await bench.read("door")).value is False
    bench.sim.push(board.set_input(8, 1))  # type: ignore[attr-defined]
    await eventually(lambda: _door_open(bench))
    await bench.close()


async def _ports_ready(driver: FirmataDriver) -> bool:
    return 0 in driver.ports and 1 in driver.ports


async def _button_is(driver: FirmataDriver, value: bool) -> bool:
    return (await driver.read("button")).value is value


async def _door_open(bench: Bench) -> bool:
    return (await bench.read("door")).value is True


async def test_outputs_pwm_and_servo_writes_with_readback() -> None:
    _driver, board, bench = make()
    await bench.connect()
    assert (await bench.read("led")).value is False
    assert (await bench.read("fan")).value == 0.0
    assert (await bench.read("arm")).value is None
    assert_done(await bench.write("led", True))
    assert board.values[13] == 1
    assert bytes([p.SET_DIGITAL_PIN_VALUE, 13, 1]) in bytes(board.received)
    assert (await bench.read("led")).value is True
    assert_done(await bench.write("relay", True))
    assert board.values[7] == 0
    assert (await bench.read("relay")).value is True
    assert_done(await bench.write("fan", "50 %"))
    assert board.modes[9] == p.PWM
    assert board.values[9] == 128
    assert (await bench.read("fan")).value == pytest.approx(50.196, abs=0.01)
    assert_done(await bench.write("arm", "90 degree"))
    assert board.servo_config[6] == (600, 2300)
    assert board.values[6] == 90
    assert (await bench.read("arm")).value == 90.0
    await bench.close()


async def test_old_firmata_uses_port_messages() -> None:
    board = FirmataBoard(version=(2, 3))
    driver, board, bench = make(board=board)
    await bench.connect()
    assert driver.protocol_version == (2, 3)
    assert_done(await bench.write("led", True))
    assert_done(await bench.write("relay", False))
    assert board.values[13] == 1
    assert board.values[7] == 1
    assert bytes([p.SET_DIGITAL_PIN_VALUE]) not in bytes(board.received)
    await bench.close()


async def test_verify_catches_a_write_the_board_ignored() -> None:
    _driver, board, bench = make()
    await bench.connect()
    board._analog_write = lambda pin, value: None  # type: ignore[method-assign]
    assert_failed(await bench.write("fan", "40 %"), "after the write")
    await bench.close()


async def test_silent_board_times_out() -> None:
    driver, board, bench = make()
    await bench.connect()
    board.ignore_queries = True
    assert_failed(await bench.write("led", True), "didn't answer")
    with pytest.raises(TimeoutError):
        await driver.read("led")
    board.analog_reporting.clear()
    driver.analog_values.clear()
    with pytest.raises(TimeoutError, match="No analog report"):
        await driver.read("light")
    await bench.close()


async def test_no_firmata_on_the_port() -> None:
    board = FirmataBoard()
    board.ignore_queries = True
    _, _, bench = make(board=board)
    with pytest.raises(DriverError, match="Upload StandardFirmata"):
        await bench.driver.connect()
    await bench.close()


async def test_disconnect_and_reconnect() -> None:
    driver, _board, bench = make()
    await bench.connect()
    bench.sim.unplug()  # type: ignore[attr-defined]
    await eventually(lambda: _down(driver))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("light")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    await eventually(lambda: _analog_ready(driver))
    assert (await bench.read("light")).value == pytest.approx(2.502, abs=0.01)
    await bench.close()


async def _down(driver: FirmataDriver) -> bool:
    return not (await driver.health()).connected


async def test_safe_state_comes_from_the_file() -> None:
    _, board, bench = make()
    await bench.connect()
    assert_done(await bench.write("led", True))
    assert_done(await bench.write("fan", "60 %"))
    assert await bench.stop() == "safe"
    assert board.values[13] == 0
    assert board.values[9] == 0
    assert board.resets == 0
    await bench.close()


async def test_describe_proposes_suggested_channels() -> None:
    driver, _, bench = make()
    assert await driver.describe() is None
    await bench.connect()
    described = await driver.describe()
    assert described is not None
    assert described["read"]["a0"]["map"] == {"pin": "A0"}
    assert described["write"]["pwm_9"]["suggested"] is True
    assert described["write"]["d13"] == {"type": "bool", "suggested": True, "map": {"pin": 13}}
    assert "d0" not in described["write"]
    await bench.close()


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { t: { unit: V } }", "needs a map"),
        ("read: { t: { unit: V, map: { pin: B2 } } }", "A0 to A15"),
        ("read: { t: { unit: V, map: { pin: 300 } } }", "between 0 and 127"),
        ("read: { t: { type: bool, map: { pin: 2, mode: analog } } }", "input or pullup"),
        ("read: { t: { unit: V, map: { pin: A0, mode: pullup } } }", "mode analog"),
        ("read: { t: { unit: degC, map: { pin: A0 } } }", "explicit scale"),
        ("read: { t: { type: string, map: { pin: 2 } } }", "bool and number"),
        ("write: { w: { unit: dimensionless, min: 0, max: 1, map: { pin: 9 } } }", "percent"),
        ("write: { w: { unit: V, min: 0, max: 1, map: { pin: 9, mode: servo } } }", "degree"),
        ("write: { w: { type: bool, map: { pin: 9, mode: pwm } } }", "mode output"),
        ("write: { w: { type: bool, map: { pin: 9, colour: red } } }", "Extra inputs"),
        ("write: { a: { type: bool, map: { pin: 9 } }, b: { type: bool, map: { pin: 9 } } }", "both use pin"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        FirmataDriver(loads(f"device: Bad\nconnect: {{ firmata: /dev/null }}\n{snippet}\n"))


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("write: { w: { unit: percent, min: 0, max: 100, map: { pin: 2 } } }", "can't do pwm"),
        ("read: { t: { unit: V, map: { pin: A9 } } }", "no analog pin"),
        ("read: { t: { unit: V, map: { pin: 5 } } }", "can't do analog"),
        ("write: { w: { type: bool, map: { pin: 40 } } }", "no pin 40"),
    ],
)
async def test_pins_are_checked_against_capabilities(snippet: str, message: str) -> None:
    text = f'device: Bad\nconnect: {{ firmata: "sim://uno", settle: 0 s, timeout: 300 ms }}\n{snippet}\n'
    driver = FirmataDriver(loads(text), opener=SerialSimulator(FirmataBoard()).opener)
    with pytest.raises(DriverError, match=message):
        await driver.connect()
    await driver.close()


@pytest.mark.parametrize(
    ("params", "message"),
    [("vref: 5", "needs a unit"), ("vref: 50 V", "at most 24"), ("sampling: 1 ms", "between"), ("x: 1", "Extra")],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(Exception, match=message):
        FirmataDriver(loads(f"device: Bad\nconnect: {{ firmata: /dev/null, {params} }}\n"))


@pytest.mark.skipif(sys.platform == "win32", reason="pty needs POSIX")
async def test_real_pyserial_on_a_pty() -> None:
    board = FirmataBoard()
    bridge = PtyBridge(board)
    try:
        file = loads(BOARD.replace('"sim://uno"', f'"{bridge.path}"'))
        driver = FirmataDriver(file)
        bench = Bench(file, driver)
        await bench.connect()
        await eventually(lambda: _analog_ready(driver))
        assert (await bench.read("light")).unit == "V"
        assert_done(await bench.write("led", True))
        assert board.values[13] == 1
        await bench.close()
    finally:
        bridge.close()
