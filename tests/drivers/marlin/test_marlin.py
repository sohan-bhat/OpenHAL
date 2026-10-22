"""The Marlin driver, against the simulated printer and a real pty."""

from __future__ import annotations

import asyncio
import re
import sys

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.marlin.driver import MarlinDriver, checksum
from openhal.drivers.marlin.simulator import MarlinPrinter
from openhal.drivers.serial.simulator import PtyBridge, SerialSimulator
from openhal.spec import loads
from tests.drivers.serial.kit import WHO, Bench, assert_done, assert_failed, eventually

PRINTER = """
device: Test printer
id: printer
connect: { marlin: "sim://marlin", timeout: 400 ms, settle: 1 s, autoreport: 1 s, action_wait: 300 ms }
read:
  extruder_temp: { unit: degC }
  bed_temp: { unit: degF }
  position_z: { unit: mm }
  sd_printing: { type: bool }
  sd_progress: { unit: percent }
  nozzle_target_seen: { unit: degC, map: { temperature: T0, field: target } }
write:
  extruder_target: { unit: degC, min: 0, max: 250 }
  bed_target: { unit: degF, min: 32, max: 212 }
  chamber_target: { unit: degC, min: 0, max: 60 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, xy, all] } } }
  pause: {}
  resume: {}
  cancel: {}
safe_state: { fan_speed: 0 }
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""


def make(text: str = PRINTER, printer: MarlinPrinter | None = None) -> tuple[MarlinDriver, MarlinPrinter, Bench]:
    model = printer or MarlinPrinter()
    sim = SerialSimulator(model)
    file = loads(text)
    driver = MarlinDriver(file, opener=sim.opener)
    bench = Bench(file, driver)
    bench.sim = sim  # type: ignore[attr-defined]
    return driver, model, bench


def numbered(model: MarlinPrinter) -> list[str]:
    """Commands the printer received, without line numbers and checksums."""
    found = []
    for line in model.received:
        match = re.fullmatch(r"N\d+ (.*)\*\d+", line)
        found.append(match.group(1) if match else line)
    return found


async def test_connect_resets_numbering_and_turns_on_autoreport() -> None:
    driver, model, bench = make()
    await bench.connect()
    commands = numbered(model)
    assert commands[:3] == ["M110 N0", "M115", "M155 S1"]
    assert driver.autoreporting
    assert re.fullmatch(r"N1 M115\*\d+", model.received[1])
    identity = await driver.identify()
    assert identity["firmware_name"].startswith("Marlin 2.1.2.4")
    assert identity["machine_type"] == "Simulated i3"
    assert identity["cap.autoreport_temp"] == "1"
    assert (await driver.health()).detail.startswith("Marlin")
    await bench.close()


def test_checksum_is_the_xor_of_every_byte() -> None:
    value = 0
    for byte in b"N123 G1 X50":
        value ^= byte
    assert checksum("N123 G1 X50") == value
    assert checksum("") == 0


async def test_reads_temperatures_positions_and_sd_state() -> None:
    _driver, model, bench = make()
    await bench.connect()
    reading = await bench.read("extruder_temp")
    assert reading.value == pytest.approx(22.0, abs=0.5)
    assert reading.unit == "degC"
    assert (await bench.read("bed_temp")).value == pytest.approx(71.6, abs=1.0)
    assert (await bench.read("position_z")).value == pytest.approx(5.0)
    assert (await bench.read("sd_printing")).value is False
    assert (await bench.read("sd_progress")).value == 0.0
    model.sd_printing, model.sd_bytes = True, (250, 1000)
    assert (await bench.read("sd_printing")).value is True
    assert (await bench.read("sd_progress")).value == 25.0
    await bench.close()


async def test_reads_use_m105_without_autoreport() -> None:
    model = MarlinPrinter()
    model.autoreport_cap = False
    driver, _, bench = make(printer=model)
    await bench.connect()
    assert not driver.autoreporting
    await bench.read("extruder_temp")
    assert "M105" in numbered(model)
    await bench.close()


async def test_heater_and_fan_writes() -> None:
    driver, model, bench = make()
    await bench.connect()
    assert_done(await bench.write("extruder_target", "200 degC"))
    assert model.targets["T0"] == 200.0
    assert "M104 T0 S200.0" in numbered(model)
    assert_done(await bench.write("bed_target", "140 degF"))
    assert model.targets["B"] == pytest.approx(60.0)
    assert_done(await bench.write("chamber_target", "40 degC"))
    assert "M141 S40.0" in numbered(model)
    assert (await bench.read("fan_speed")).value is None
    assert_done(await bench.write("fan_speed", "50 %"))
    assert model.fans[0] == 128
    assert (await bench.read("fan_speed")).value == 50.0
    driver.temps_at = 0.0
    assert (await bench.read("extruder_target")).value == 200.0
    assert (await bench.read("nozzle_target_seen")).value == 200.0
    await bench.close()


async def test_resend_after_a_checksum_error() -> None:
    _, model, bench = make()
    await bench.connect()
    model.corrupt_next_line = True
    assert_done(await bench.write("extruder_target", "180 degC"))
    assert model.targets["T0"] == 180.0
    assert sum("checksum" in line for line in model.received) == 0
    assert_done(await bench.write("extruder_target", "190 degC"))
    assert model.targets["T0"] == 190.0
    await bench.close()


async def test_unknown_command_fails_the_write() -> None:
    model = MarlinPrinter()
    model.unsupported = {"M141"}
    _, _, bench = make(printer=model)
    await bench.connect()
    assert_failed(await bench.write("chamber_target", "40 degC"), "doesn't support M141")
    assert_done(await bench.write("extruder_target", "10 degC"))
    await bench.close()


async def test_home_waits_or_returns_started_while_busy() -> None:
    _driver, model, bench = make()
    await bench.connect()
    assert_done(await bench.act("home", axes="z"))
    assert "G28 Z" in numbered(model)
    model.position["Z"] = 7.0
    model.home_time_s = 1.0
    model.busy_every_s = 0.1
    started = asyncio.get_running_loop().time()
    assert_done(await bench.act("home", axes="all"))
    assert asyncio.get_running_loop().time() - started < 0.9
    assert (await bench.read("extruder_temp")).value == pytest.approx(22.0, abs=0.5)
    await eventually(lambda: _homed(model), within=3.0)
    assert (await bench.read("position_z")).value == 0.0
    await bench.close()


async def _homed(model: MarlinPrinter) -> bool:
    return model.position["Z"] == 0.0


async def test_sd_print_actions() -> None:
    _, model, bench = make()
    await bench.connect()
    model.sd_printing, model.sd_bytes = True, (10, 100)
    assert_done(await bench.act("pause"))
    assert model.sd_paused
    assert_done(await bench.act("resume"))
    assert model.sd_printing
    assert_done(await bench.act("cancel"))
    assert not model.sd_printing
    assert numbered(model)[-3:] == ["M25", "M24", "M524"]
    await bench.close()


async def test_native_safe_state_turns_heaters_off_without_m112() -> None:
    _, model, bench = make()
    await bench.connect()
    assert_done(await bench.write("extruder_target", "200 degC"))
    assert_done(await bench.write("bed_target", "140 degF"))
    assert_done(await bench.write("fan_speed", "50 %"))
    assert await bench.stop() == "safe"
    assert model.targets["T0"] == 0.0
    assert model.targets["B"] == 0.0
    assert model.targets["C"] == 0.0
    assert model.fans[0] == 0
    assert "M112" not in numbered(model)
    assert not model.halted
    await bench.close()


async def test_m112_only_when_enabled() -> None:
    driver, model, bench = make(PRINTER.replace("action_wait: 300 ms", "action_wait: 300 ms, m112_on_stop: true"))
    await bench.connect()
    await bench.kernel.stop_all(WHO, "test")
    assert "M112" in numbered(model)
    await eventually(lambda: _down(driver))
    assert "halted" in (await driver.health()).detail
    with pytest.raises(DriverError, match="firmware stopped"):
        await driver.read("position_z")
    await bench.close()


async def _down(driver: MarlinDriver) -> bool:
    return not (await driver.health()).connected


async def test_printer_reset_fails_commands_in_flight() -> None:
    driver, model, bench = make()
    await bench.connect()
    model.home_time_s = 5.0
    task = asyncio.create_task(bench.act("home", axes="all"))
    await asyncio.sleep(0.05)
    bench.sim.push(model.reset())  # type: ignore[attr-defined]
    decision = await task
    assert decision.status in ("done", "failed")
    await eventually(lambda: _idle(driver))
    assert_done(await bench.write("extruder_target", "20 degC"))
    await bench.close()


async def _idle(driver: MarlinDriver) -> bool:
    return not driver._inflight


async def test_silent_printer_times_out() -> None:
    driver, model, bench = make()
    await bench.connect()
    bench.sim.silent = True  # type: ignore[attr-defined]
    model.autoreport_s = 0
    driver.temps_at = 0.0
    with pytest.raises(TimeoutError, match="didn't acknowledge M105"):
        await driver.read("extruder_temp")
    assert_failed(await bench.write("extruder_target", "20 degC"), "didn't acknowledge")
    await bench.close()


async def test_garbled_ok_is_not_taken_as_an_answer() -> None:
    driver, model, bench = make()
    await bench.connect()
    model.corrupt_next_ok = True
    with pytest.raises(TimeoutError):
        await driver.read("position_z")
    await bench.close()


async def test_disconnect_and_reconnect() -> None:
    driver, _, bench = make()
    await bench.connect()
    bench.sim.unplug()  # type: ignore[attr-defined]
    await eventually(lambda: _down(driver))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("position_z")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert (await bench.read("position_z")).value == pytest.approx(5.0)
    await bench.close()


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { mystery: { unit: degC } }", "not a Marlin channel"),
        ("read: { t: { unit: degC, map: { temperature: X9 } } }", "should match pattern"),
        ("read: { t: { unit: degC, map: { temperature: T0, position: X } } }", "exactly one"),
        ("read: { extruder_temp: { unit: V } }", "converts to degC"),
        ("write: { fan_speed: { unit: dimensionless, min: 0, max: 255 } }", "percent"),
        ("write: { w: { unit: degC, min: 0, max: 1, map: { heater: B, fan: 1 } } }", "exactly one"),
        ("write: { w: { unit: degC, min: 0, max: 1, map: { gcode: M104 } } }", "Extra inputs"),
        ("actions: { home: { args: { speed: { unit: mm/s, min: 0, max: 1 } } } }", "only an axes"),
        ("actions: { dance: {} }", "not a Marlin channel"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MarlinDriver(loads(f"device: Bad\nconnect: {{ marlin: /dev/null }}\n{snippet}\n"))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("baud: 300", "greater than"),
        ("timeout: 2", "needs a unit"),
        ("action_wait: 20 s", "between"),
        ("x: 1", "Extra"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(Exception, match=message):
        MarlinDriver(loads(f"device: Bad\nconnect: {{ marlin: /dev/null, {params} }}\n"))


async def test_discover_lists_usb_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    ports = [
        SimpleNamespace(device="/dev/ttyUSB0", vid=0x1A86, pid=0x7523, serial_number=None),
        SimpleNamespace(device="/dev/ttyS0", vid=None, pid=None, serial_number=None),
    ]
    monkeypatch.setattr("openhal.drivers.marlin.driver.list_serial_ports", lambda: ports)
    found = await MarlinDriver.discover()
    assert [item.address for item in found] == ["/dev/ttyUSB0"]


@pytest.mark.skipif(sys.platform == "win32", reason="pty needs POSIX")
async def test_real_pyserial_on_a_pty() -> None:
    model = MarlinPrinter()
    bridge = PtyBridge(model)
    try:
        text = PRINTER.replace('"sim://marlin"', f'"{bridge.path}"').replace("settle: 1 s", "settle: 200 ms")
        file = loads(text)
        driver = MarlinDriver(file)
        bench = Bench(file, driver)
        await bench.connect()
        assert (await bench.read("position_z")).value == pytest.approx(5.0)
        assert_done(await bench.write("extruder_target", "30 degC"))
        assert model.targets["T0"] == 30.0
        await bench.close()
    finally:
        bridge.close()
