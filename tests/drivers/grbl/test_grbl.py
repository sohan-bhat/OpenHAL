"""The GRBL driver, against the simulated controller and a real pty."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.grbl.driver import GrblDriver
from openhal.drivers.grbl.simulator import GrblMachine
from openhal.drivers.serial.simulator import PtyBridge, SerialSimulator
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

STATES = "[idle, run, hold, jog, alarm, door, check, home, sleep]"
CNC = f"""
device: Test router
id: cnc
connect: {{ grbl: "sim://grbl", timeout: 400 ms, settle: 1 s, action_wait: 2 s, status_age: 0 s }}
read:
  state: {{ type: enum, values: {STATES} }}
  alarm: {{ unit: dimensionless }}
  position_x: {{ unit: mm }}
  position_z: {{ unit: cm }}
  work_x: {{ unit: mm }}
  feed_rate: {{ unit: mm/min }}
  pins: {{ type: string }}
  max_x: {{ unit: mm, map: {{ setting: 130 }} }}
  soft_limits: {{ type: bool, map: {{ setting: 20 }} }}
write:
  spindle_speed: {{ unit: rpm, min: 0, max: 1000 }}
  flood: {{ type: bool }}
  mist: {{ type: bool }}
actions:
  home: {{}}
  jog: {{ args: {{ x: {{ unit: mm, min: -50, max: 50 }}, feed: {{ unit: mm/min, min: 1, max: 3000 }} }} }}
  move:
    args: {{ x: {{ unit: mm, min: -300, max: 300 }}, y: {{ unit: mm, min: -300, max: 300 }},
             feed: {{ unit: mm/min, min: 1, max: 3000 }} }}
  rapid: {{ args: {{ z: {{ unit: mm, min: -80, max: 0 }} }}, map: {{ command: move, rapid: true, frame: machine }} }}
  set_work_zero: {{ args: {{ axes: {{ type: enum, values: [x, xy, all] }} }} }}
  cancel_jog: {{}}
  hold: {{}}
  resume: {{}}
  clear_alarm: {{}}
  reset: {{}}
safe_state: {{ spindle_speed: 0, flood: false }}
hazard: high
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


def make(text: str = CNC, machine: GrblMachine | None = None) -> tuple[GrblDriver, GrblMachine, Bench, SerialSimulator]:
    model = machine or GrblMachine()
    model.time_scale = 50
    sim = SerialSimulator(model)
    file = loads(text)
    driver = GrblDriver(file, opener=sim.opener)
    return driver, model, Bench(file, driver), sim


async def test_connect_reads_build_info_and_settings() -> None:
    driver, model, bench, _ = make()
    await bench.connect()
    assert model.received[:2] == ["$I", "$$"]
    identity = await driver.identify()
    assert identity["version"] == "1.1h"
    assert identity["build"] == "20190830"
    assert identity["options"] == "V,15,128"
    assert identity["banner"] == "Grbl 1.1h"
    assert driver.grbl[130] == 300.0
    assert (await driver.health()).detail == "Grbl 1.1h, idle"
    await bench.close()


async def test_reads_status_positions_and_settings() -> None:
    _driver, model, bench, _ = make()
    model.mpos = [12.5, -3.0, -20.0]
    model.g54 = [2.5, 0.0, 0.0]
    await bench.connect()
    assert (await bench.read("state")).value == "idle"
    assert (await bench.read("alarm")).value == 0
    assert (await bench.read("position_x")).value == pytest.approx(12.5)
    reading = await bench.read("position_z")
    assert (reading.value, reading.unit) == (pytest.approx(-2.0), "cm")
    assert (await bench.read("work_x")).value == pytest.approx(10.0)
    assert (await bench.read("feed_rate")).value == 0.0
    assert (await bench.read("pins")).value == ""
    assert (await bench.read("max_x")).value == 300.0
    assert (await bench.read("soft_limits")).value is False
    await bench.close()


async def test_work_position_reports_use_the_offsets_from_dollar_hash() -> None:
    driver, model, bench, _ = make()
    model.settings[10] = 0
    model.mpos = [30.0, 0.0, 0.0]
    model.g54 = [10.0, 0.0, 0.0]
    model.g92 = [5.0, 0.0, 0.0]
    model.reports = 5
    await bench.connect()
    assert driver.session is not None
    driver.session.wco = None
    model.reports = 5
    assert (await bench.read("position_x")).value == pytest.approx(30.0)
    assert "$#" in model.received
    assert (await bench.read("work_x")).value == pytest.approx(15.0)
    await bench.close()


async def test_inch_reports_are_converted() -> None:
    _driver, model, bench, _ = make()
    model.settings[13] = 1
    model.mpos = [25.4, 0.0, 0.0]
    await bench.connect()
    assert (await bench.read("position_x")).value == pytest.approx(25.4)
    assert (await bench.read("max_x")).value == 300.0
    await bench.close()


async def test_spindle_writes_and_readback() -> None:
    driver, model, bench, sim = make()
    await bench.connect()
    assert_done(await bench.write("spindle_speed", "600 rpm"))
    assert model.received[-1] == "M3 S600"
    assert (await bench.read("spindle_speed")).value == 600.0
    assert_done(await bench.write("spindle_speed", "0 rpm"))
    assert model.received[-1] == "M5"
    assert model.spindle == "M5"
    model.settings[30] = 500
    driver.grbl[30] = 500
    sent = len(sim.written)
    assert_failed(await bench.write("spindle_speed", "800 rpm"), "above this controller's $30")
    driver.grbl[31] = 100
    assert_failed(await bench.write("spindle_speed", "50 rpm"), "below the $31 of 100 rpm")
    assert all(b"M3" not in chunk for chunk in sim.written[sent:])
    await bench.close()


async def test_counter_clockwise_spindle_uses_m4() -> None:
    text = CNC.replace(
        "spindle_speed: { unit: rpm, min: 0, max: 1000 }",
        "spindle_speed: { unit: rpm, min: 0, max: 1000, map: { spindle: ccw } }",
    )
    _driver, model, bench, _ = make(text)
    await bench.connect()
    assert_done(await bench.write("spindle_speed", "300 rpm"))
    assert model.received[-1] == "M4 S300"
    await bench.close()


LASER = f"""
device: Test laser
id: laser
connect: {{ grbl: "sim://grbl", timeout: 400 ms, settle: 1 s, status_age: 0 s }}
read:
  state: {{ type: enum, values: {STATES} }}
write:
  laser_power: {{ unit: percent, min: 0, max: 60 }}
safe_state: {{ laser_power: 0 }}
hazard: high
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


async def test_laser_power_scales_to_max_spindle_speed() -> None:
    _driver, model, bench, _ = make(LASER, GrblMachine(laser=True))
    await bench.connect()
    assert_done(await bench.write("laser_power", "50 %"))
    assert model.received[-1] == "M4 S500"
    assert (await bench.read("laser_power")).value == pytest.approx(50.0)
    assert_done(await bench.write("laser_power", "0 %"))
    assert model.received[-1] == "M5"
    await bench.close()


async def test_laser_power_needs_laser_mode() -> None:
    _driver, _, bench, _ = make(LASER, GrblMachine(laser=False))
    with pytest.raises(DriverError, match=r"needs laser mode"):
        await bench.connect()
    await bench.close()


async def test_coolant_on_and_off_keeps_the_other_output() -> None:
    _driver, model, bench, _ = make()
    await bench.connect()
    assert_done(await bench.write("flood", True))
    assert_done(await bench.write("mist", True))
    assert model.coolant == {"M7", "M8"}
    assert_done(await bench.write("flood", False))
    assert model.coolant == {"M7"}
    assert model.received[-2:] == ["M9", "M7"]
    assert (await bench.read("mist")).value is True
    assert (await bench.read("flood")).value is False
    await bench.close()


async def test_jog_runs_and_reports_done() -> None:
    _driver, model, bench, _ = make()
    await bench.connect()
    decision = await bench.act("jog", x="10 mm", feed="3000 mm/min")
    assert_done(decision)
    assert "$J=G21 G91 X10 F3000" in model.received
    assert model.mpos[0] == pytest.approx(10.0)
    assert (await bench.read("position_x")).value == pytest.approx(10.0)
    await bench.close()


async def test_jog_beyond_travel_is_refused_by_grbl() -> None:
    _driver, model, bench, _ = make(machine=GrblMachine(soft_limits=True))
    await bench.connect()
    assert_failed(await bench.act("jog", x="10 mm", feed="600 mm/min"), "error:15")
    assert model.state == "Idle"
    await bench.close()


async def test_long_move_returns_started_then_finishes() -> None:
    text = CNC.replace("action_wait: 2 s", "action_wait: 200 ms")
    _driver, model, bench, _ = make(text)
    await bench.connect()
    model.time_scale = 1
    decision = await bench.act("move", x="5 mm", y="0 mm", feed="60 mm/min")
    assert_done(decision)
    assert "G21 G90 G1 X5 Y0 F60" in model.received
    assert model.state == "Run"
    assert_done(await bench.act("hold"))
    assert model.state == "Hold:0"
    assert (await bench.read("state")).value == "hold"
    assert_done(await bench.act("resume"))
    model.time_scale = 100
    await eventually(lambda: asyncio.sleep(0, model.state == "Idle"))
    await bench.close()


async def test_rapid_move_in_machine_coordinates() -> None:
    _driver, model, bench, _ = make()
    await bench.connect()
    assert_done(await bench.act("rapid", z="-5 mm"))
    assert "G21 G90 G53 G0 Z-5" in model.received
    assert model.mpos[2] == pytest.approx(-5.0)
    await bench.close()


async def test_soft_limit_alarm_blocks_until_reset() -> None:
    driver, _model, bench, _ = make(machine=GrblMachine(soft_limits=True))
    await bench.connect()
    assert_failed(await bench.act("move", x="10 mm", y="0 mm", feed="600 mm/min"), "ALARM:2")
    assert driver.session is not None
    assert driver.session.critical
    assert (await bench.read("state")).value == "alarm"
    assert (await bench.read("alarm")).value == 2
    assert "waiting for a reset" in (await driver.health()).detail
    assert_failed(await bench.act("clear_alarm"), "waiting for a reset")
    assert_done(await bench.act("reset"))
    assert not driver.session.critical
    assert_done(await bench.act("clear_alarm"))
    assert (await bench.read("state")).value == "idle"
    await bench.close()


async def test_homing_from_the_boot_alarm() -> None:
    driver, model, bench, _ = make(machine=GrblMachine(homing=True))
    await bench.connect()
    assert driver.session is not None
    assert driver.session.message == "'$H'|'$X' to unlock"
    assert (await bench.read("state")).value == "alarm"
    assert_failed(await bench.write("spindle_speed", "100 rpm"), "error:9")
    assert_done(await bench.act("home"))
    assert model.state == "Idle"
    assert_done(await bench.write("spindle_speed", "100 rpm"))
    await bench.close()


async def test_slow_homing_returns_started() -> None:
    text = CNC.replace("action_wait: 2 s", "action_wait: 100 ms")
    machine = GrblMachine(homing=True)
    _driver, model, bench, _ = make(text, machine)
    await bench.connect()
    model.home_time_s = 50.0
    assert_done(await bench.act("home"))
    assert model.state == "Home"
    assert (await bench.read("state")).value == "home"
    await bench.close()


async def test_home_without_homing_enabled_fails() -> None:
    _driver, _model, bench, _ = make()
    await bench.connect()
    assert_failed(await bench.act("home"), "homing is not enabled")
    await bench.close()


async def test_stop_while_moving_holds_then_resets_into_alarm() -> None:
    text = CNC.replace("action_wait: 2 s", "action_wait: 100 ms")
    _driver, model, bench, _ = make(text)
    await bench.connect()
    model.time_scale = 1
    assert_done(await bench.write("spindle_speed", "800 rpm"))
    assert_done(await bench.write("flood", True))
    assert_done(await bench.act("move", x="100 mm", y="0 mm", feed="60 mm/min"))
    assert model.state == "Run"
    before = len(model.realtime)
    assert await bench.stop() == "safe"
    during = [byte for byte in model.realtime[before:] if byte != b"?"]
    assert during == [b"!", b"\x18"]
    assert "M5" in model.received
    assert model.state == "Alarm"
    assert model.spindle == "M5"
    assert model.coolant == set()
    assert (await bench.read("alarm")).value == 3
    await bench.close()


async def test_stop_while_idle_resets_without_an_alarm() -> None:
    _driver, model, bench, _ = make()
    await bench.connect()
    assert_done(await bench.write("spindle_speed", "200 rpm"))
    assert await bench.stop() == "safe"
    assert model.state == "Idle"
    assert model.spindle == "M5"
    await bench.close()


async def test_hard_limit_fails_commands_and_needs_a_reset() -> None:
    driver, model, bench, sim = make()
    await bench.connect()
    model.trip_hard_limit()
    sim.push(model.poll(0.0))
    await eventually(lambda: asyncio.sleep(0, driver.session is not None and driver.session.critical))
    assert (await bench.read("alarm")).value == 1
    assert "hard limit" in (await driver.health()).detail
    assert await bench.stop() == "safe"
    assert model.state == "Alarm"
    assert not model.critical
    await bench.close()


async def test_set_work_zero_and_jog_cancel() -> None:
    driver, model, bench, _ = make()
    model.mpos = [40.0, 5.0, 0.0]
    await bench.connect()
    assert_done(await bench.act("set_work_zero", axes="xy"))
    assert "G10 L20 P0 X0 Y0" in model.received
    assert (await bench.read("work_x")).value == pytest.approx(0.0)
    text_wait = driver.settings.action_wait
    driver.settings = driver.settings.model_copy(update={"action_wait": 0.1})
    model.time_scale = 1
    assert_done(await bench.act("jog", x="20 mm", feed="60 mm/min"))
    assert model.state == "Jog"
    assert_done(await bench.act("cancel_jog"))
    assert model.realtime[-1] == b"\x85"
    assert model.state == "Idle"
    assert text_wait == 2.0
    await bench.close()


async def test_controller_reset_fails_the_command_in_flight() -> None:
    driver, _model, bench, sim = make()
    await bench.connect()
    sim.silent = True
    task = asyncio.create_task(bench.write("spindle_speed", "100 rpm"))
    await eventually(lambda: asyncio.sleep(0, driver.session is not None and driver.session.inflight > 0))
    sim.push(b"\r\nGrbl 1.1h ['$' for help]\r\n")
    decision = await task
    assert_failed(decision, "controller reset")
    sim.silent = False
    await bench.close()


async def test_silent_controller_times_out() -> None:
    driver, _model, bench, sim = make()
    await bench.connect()
    sim.silent = True
    with pytest.raises(TimeoutError):
        await driver.read("state")
    health = await driver.health()
    assert not health.connected
    assert "status query" in health.detail
    await bench.close()


async def test_malformed_status_report_raises() -> None:
    driver, _model, bench, sim = make()
    await bench.connect()
    sim.garble = True
    with pytest.raises(DriverError, match="status report the driver can't read"):
        await driver.read("position_x")
    sim.garble = False
    assert (await driver.read("position_x")).value == 0.0
    sim.push(b"error:\r\nok\r\nGarbage line\r\n")
    assert (await driver.read("state")).value == "idle"
    await bench.close()


async def test_disconnect_and_reconnect() -> None:
    driver, _model, bench, sim = make()
    await bench.connect()
    sim.unplug()
    await eventually(lambda: _disconnected(driver))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("state")
    await bench.connect()
    assert (await bench.read("state")).value == "idle"
    assert sim.opened == 2
    await bench.close()


async def _disconnected(driver: GrblDriver) -> bool:
    return not (await driver.health()).connected


async def test_describe_proposes_suggested_limits_from_settings() -> None:
    driver, _model, bench, _ = make(machine=GrblMachine(homing=True, soft_limits=True))
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["spindle_speed"]["max"] == 1000
    assert all(entry["suggested"] for entry in proposal["write"].values())
    assert all(entry["suggested"] for entry in proposal["actions"].values())
    assert proposal["actions"]["move"]["args"]["x"] == {"unit": "mm", "min": -300.0, "max": 0}
    assert "home" in proposal["actions"]
    assert proposal["safe_state"] == [{"spindle_speed": 0, "flood": False}]
    laser_driver, _, laser_bench, _ = make(LASER, GrblMachine(laser=True))
    await laser_bench.connect()
    laser = await laser_driver.describe()
    assert laser is not None
    assert "laser_power" in laser["write"]
    await bench.close()
    await laser_bench.close()


async def test_describe_needs_a_connection() -> None:
    driver, _, _, _ = make()
    assert await driver.describe() is None
    assert await driver.identify() == {"port": "sim://grbl"}


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { spindle_temp: { unit: degC } }", "not a GRBL channel"),
        ("read: { state: { type: enum, values: [idle, flying] } }", "never reports"),
        ("read: { state: { unit: mm } }", "enum or a string"),
        ("read: { position_x: { unit: degC } }", "converts to mm"),
        ("read: { pins: { unit: mm } }", "pins is a string"),
        ("read: { feed_rate: { unit: mm } }", "converts to mm/min"),
        ("read: { max_x: { type: string, map: { setting: 130 } } }", "read as a number"),
        ("read: { both: { unit: mm, map: { setting: 130, status: x } } }", "exactly one"),
        ("write: { laser_power: { unit: rpm, min: 0, max: 10 } }", "laser power is in percent"),
        ("write: { flood: { unit: percent, min: 0, max: 1 } }", "true or false"),
        ("write: { spindle_speed: { type: bool } }", "are numbers"),
        ("write: { spindle_speed: { unit: mm, min: 0, max: 10 } }", "converts to rpm"),
        ("actions: { jog: { args: { x: { unit: mm, min: 0, max: 1 } } } }", "needs a feed"),
        ("actions: { jog: { args: { feed: { unit: mm/min, min: 1, max: 2 } } } }", "at least one axis"),
        ("actions: { jog: { args: { q: { unit: mm, min: 0, max: 1 } } } }", "axis arguments"),
        (
            "actions: { jog: { args: { x: { unit: s, min: 0, max: 1 }, feed: { unit: mm/min, min: 1, max: 2 } } } }",
            "converts to mm",
        ),
        ("actions: { hold: { args: { x: { unit: mm, min: 0, max: 1 } } } }", "takes no arguments"),
        ("actions: { set_work_zero: { args: { axes: { type: enum, values: [x, w] } } } }", "must be an enum"),
        ("actions: { dance: {} }", "not a GRBL channel"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f'device: Bad\nid: bad\nconnect: {{ grbl: "sim://grbl" }}\n{snippet}\n'
    with pytest.raises(DriverError, match=message):
        GrblDriver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"),
    [("timeout: 0 s", "timeout"), ("action_wait: 30 s", "action_wait"), ("status_age: 5 s", "status_age")],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        GrblDriver(loads(f'device: Bad\nid: bad\nconnect: {{ grbl: "sim://grbl", {params} }}\n'))


async def test_discover_lists_usb_ports_without_opening_them(monkeypatch: pytest.MonkeyPatch) -> None:
    class Port:
        device = "/dev/ttyUSB0"
        vid, pid = 0x1A86, 0x7523
        serial_number = "A1"
        manufacturer = "QinHeng"
        product = "USB Serial"
        description = "USB Serial"

    class Builtin:
        device = "/dev/ttyS0"
        vid = None

    monkeypatch.setattr("openhal.drivers.grbl.driver.list_serial_ports", lambda: [Port(), Builtin()])
    found = await GrblDriver.discover()
    assert [item.address for item in found] == ["/dev/ttyUSB0"]
    assert found[0].identifiers["usb"] == "1a86:7523"


@pytest.mark.skipif(sys.platform == "win32", reason="pty needs POSIX")
async def test_real_pyserial_on_a_pty() -> None:
    model = GrblMachine()
    bridge = PtyBridge(model)
    try:
        text = CNC.replace('"sim://grbl"', f'"{bridge.path}"').replace("settle: 1 s", "settle: 200 ms")
        file = loads(text)
        driver = GrblDriver(file)
        bench = Bench(file, driver)
        await bench.connect()
        assert (await bench.read("state")).value == "idle"
        assert_done(await bench.write("spindle_speed", "250 rpm"))
        assert model.spindle == "M3"
        await bench.close()
    finally:
        bridge.close()


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/grbl/examples/3018-router.hal.yaml")
    assert not file.writable
    assert file.effective_hazard == "high"
    driver = GrblDriver(file)
    assert set(driver.actions) == {"home", "jog", "cancel_jog", "hold", "resume", "clear_alarm"}
