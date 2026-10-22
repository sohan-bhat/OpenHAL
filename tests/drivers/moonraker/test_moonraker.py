"""The Moonraker driver over HTTP (mock transport) and WebSocket (a real local server)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.moonraker.driver import MoonrakerDriver
from openhal.drivers.moonraker.simulator import MoonrakerSim
from openhal.spec import loads
from openhal.spec.loader import from_data
from tests.drivers.serial.kit import WHO, Bench, assert_done, assert_failed, eventually

PRINTER = """
device: Voron
id: voron
match: {{ moonraker: {{ hostname: "{hostname}" }} }}
connect: {{ moonraker: 127.0.0.1, port: {port}, timeout: 400 ms, action_wait: 300 ms{extra} }}
read:
  state: {{ type: enum, values: [standby, printing, paused, complete, cancelled, error] }}
  klippy_state: {{ type: string }}
  extruder_temp: {{ unit: degC }}
  bed_temp: {{ unit: degF }}
  chamber_temp: {{ unit: degC }}
  enclosure_temp: {{ unit: degC, map: {{ object: heater_generic enclosure, field: temperature }} }}
  progress: {{ unit: percent }}
  position_z: {{ unit: mm }}
  homed_axes: {{ type: string }}
write:
  extruder_target: {{ unit: degC, min: 0, max: 300 }}
  bed_target: {{ unit: degC, min: 0, max: 110 }}
  enclosure_target: {{ unit: degC, min: 0, max: 60, map: {{ heater: enclosure }} }}
  fan_speed: {{ unit: percent, min: 0, max: 100 }}
  exhaust: {{ unit: percent, min: 0, max: 100, map: {{ fan: exhaust }} }}
actions:
  home: {{ args: {{ axes: {{ type: enum, values: [x, y, z, xy, all] }} }} }}
  pause: {{}}
  resume: {{}}
  cancel: {{}}
safe_state:
  - {{ fan_speed: 0 }}
hazard: medium
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


def text(port: int = 7125, *, hostname: str = "voron*", extra: str = "") -> str:
    return PRINTER.format(port=port, hostname=hostname, extra=extra)


def http_bench(sim: MoonrakerSim, **kwargs: str) -> Bench:
    file = loads(text(**kwargs))
    return Bench(file, MoonrakerDriver(file, http_transport=sim.http_transport()))


@pytest.fixture
async def ws_sim() -> AsyncIterator[MoonrakerSim]:
    sim = MoonrakerSim()
    await sim.start_websocket()
    yield sim
    await sim.close()


def ws_bench(sim: MoonrakerSim) -> Bench:
    assert sim.port is not None
    file = loads(text(sim.port, extra=", transport: websocket"))
    return Bench(file, MoonrakerDriver(file))


# ---------------------------------------------------------------------- HTTP


async def test_http_reads_every_convention() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    objects = sim.state.objects
    objects["print_stats"]["state"] = "printing"
    objects["virtual_sdcard"]["progress"] = 0.425
    assert (await bench.read("state")).value == "printing"
    assert (await bench.read("klippy_state")).value == "ready"
    assert (await bench.read("extruder_temp")).value == pytest.approx(22.0, abs=0.5)
    bed = await bench.read("bed_temp")
    assert bed.unit == "degF"
    assert bed.value == pytest.approx(70.7, abs=1.0)
    assert (await bench.read("chamber_temp")).value == pytest.approx(24.0)
    assert (await bench.read("enclosure_temp")).value == pytest.approx(23.0, abs=0.5)
    assert (await bench.read("progress")).value == pytest.approx(42.5)
    assert (await bench.read("position_z")).value == 5.0
    assert (await bench.read("homed_axes")).value == ""
    identity = await bench.driver.identify()
    assert identity["hostname"] == "voron-sim"
    await bench.close()


async def test_http_writes_use_klipper_gcode() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    objects = sim.state.objects
    assert_done(await bench.write("extruder_target", "210 degC"))
    assert objects["extruder"]["target"] == 210.0
    assert "SET_HEATER_TEMPERATURE HEATER=extruder TARGET=210.0" in sim.state.gcode
    assert (await bench.read("extruder_target")).value == 210.0
    assert_done(await bench.write("bed_target", "60 degC"))
    assert objects["heater_bed"]["target"] == 60.0
    assert_done(await bench.write("enclosure_target", "40 degC"))
    assert objects["heater_generic enclosure"]["target"] == 40.0
    assert_done(await bench.write("fan_speed", "50 %"))
    assert "M106 S128" in sim.state.gcode
    assert (await bench.read("fan_speed")).value == pytest.approx(50.2, abs=0.1)
    assert_done(await bench.write("exhaust", "25 %"))
    assert objects["fan_generic exhaust"]["speed"] == 0.25
    assert (await bench.read("exhaust")).value == 25.0
    await bench.close()


async def test_klipper_errors_fail_commands() -> None:
    sim = MoonrakerSim()
    sim.state.objects["configfile"]["settings"]["extruder"]["max_temp"] = 200
    bench = await http_bench(sim).connect()
    assert_failed(await bench.write("extruder_target", "250 degC"), "out of range")
    assert_failed(await bench.act("pause"), "Print is not in progress")
    sim.state.objects["print_stats"]["state"] = "printing"
    assert_done(await bench.act("pause"))
    assert_done(await bench.act("resume"))
    assert_done(await bench.act("cancel"))
    assert sim.state.objects["print_stats"]["state"] == "cancelled"
    await bench.close()


async def test_home_waits_or_returns_started() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    assert_done(await bench.act("home", axes="z"))
    assert sim.state.objects["toolhead"]["homed_axes"] == "z"
    sim.state.home_time_s = 0.8
    loop = asyncio.get_running_loop()
    started = loop.time()
    decision = await bench.act("home", axes="all")
    assert_done(decision)
    assert loop.time() - started < 0.7
    await eventually(lambda: _homed(sim), within=3.0)
    await bench.close()


async def _homed(sim: MoonrakerSim) -> bool:
    return sim.state.objects["toolhead"]["homed_axes"] == "xyz"


async def test_native_safe_state_turns_heaters_off() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    assert_done(await bench.write("extruder_target", "200 degC"))
    assert_done(await bench.write("enclosure_target", "40 degC"))
    assert await bench.stop() == "safe"
    assert "TURN_OFF_HEATERS" in sim.state.gcode
    assert sim.state.objects["extruder"]["target"] == 0.0
    assert sim.state.objects["heater_generic enclosure"]["target"] == 0.0
    assert sim.klippy_state == "ready"
    await bench.close()


async def test_emergency_stop_only_when_enabled() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim, extra=", emergency_stop_on_stop: true").connect()
    await bench.kernel.stop_all(WHO, "test")
    assert "printer.emergency_stop" in sim.calls
    assert sim.klippy_state == "shutdown"
    health = await bench.driver.health()
    assert not health.connected
    assert "Timer too close" in health.detail
    await bench.close()


async def test_klippy_shutdown_blocks_writes() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    sim.klippy_state = "shutdown"
    health = await bench.driver.health()
    assert not health.connected
    assert "shutdown" in health.detail
    assert (await bench.driver.read("klippy_state")).value == "shutdown"
    sim.klippy_state = "disconnected"
    with pytest.raises(DriverError, match="Klippy Disconnected"):
        await bench.driver.read("extruder_temp")
    await bench.close()


async def test_gcode_refused_while_klippy_is_not_ready() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    sim.state.objects["webhooks"]["state"] = "startup"
    with pytest.raises(DriverError, match="Klippy is not ready"):
        await _gcode(bench)
    await bench.close()


async def test_api_key_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = MoonrakerSim()
    sim.api_key = "s3cret"
    bench = http_bench(sim, extra=", token_env: MOONRAKER_KEY")
    monkeypatch.delenv("MOONRAKER_KEY", raising=False)
    with pytest.raises(DriverError, match="Set the MOONRAKER_KEY"):
        await bench.driver.connect()
    monkeypatch.setenv("MOONRAKER_KEY", "wrong")
    with pytest.raises(DriverError, match="wants an API key"):
        await bench.driver.connect()
    monkeypatch.setenv("MOONRAKER_KEY", "s3cret")
    await bench.connect()
    assert (await bench.read("state")).value == "standby"
    await bench.close()


async def test_hostname_must_match() -> None:
    bench = http_bench(MoonrakerSim(), hostname="ender*")
    with pytest.raises(DriverError, match=r"doesn't match match\.moonraker"):
        await bench.driver.connect()
    await bench.close()


async def test_http_faults() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    sim.latency_s = 1.0
    with pytest.raises(TimeoutError, match=r"didn't answer printer\.objects\.query"):
        await bench.driver.read("extruder_temp")
    sim.latency_s = 0.0
    sim.malformed = True
    with pytest.raises(DriverError, match="not JSON"):
        await bench.driver.read("extruder_temp")
    sim.malformed = False
    sim.fail_http = True
    with pytest.raises(DriverError, match="Could not reach Moonraker"):
        await bench.driver.read("extruder_temp")
    assert not (await bench.driver.health()).connected
    sim.fail_http = False
    assert (await bench.driver.health()).connected
    del sim.state.objects["temperature_sensor chamber"]
    with pytest.raises(DriverError, match="has no object"):
        await bench.driver.read("chamber_temp")
    sim.state.objects["print_stats"]["state"] = "exploded"
    with pytest.raises(DriverError, match="not one of"):
        await bench.driver.read("state")
    await bench.close()


async def test_not_connected() -> None:
    driver = MoonrakerDriver(loads(text()))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("state")
    assert not (await driver.health()).connected
    assert await driver.describe() is None


async def test_describe_proposes_channels_from_printer_objects() -> None:
    sim = MoonrakerSim()
    bench = await http_bench(sim).connect()
    proposal = await bench.driver.describe()
    assert proposal is not None
    assert proposal["write"]["extruder_target"]["max"] == 280
    assert proposal["write"]["bed_target"]["map"] == {"heater": "heater_bed"}
    assert proposal["write"]["enclosure_target"]["map"] == {"heater": "enclosure"}
    assert proposal["write"]["exhaust_fan"]["map"] == {"fan": "exhaust"}
    assert proposal["read"]["chamber_temp"]["map"]["object"] == "temperature_sensor chamber"
    assert proposal["match"] == {"moonraker": {"hostname": "voron-sim"}}
    for section in ("write", "actions"):
        assert all(entry["suggested"] for entry in proposal[section].values())
    data = {**proposal, "connect": {"moonraker": "127.0.0.1"}}
    file = from_data(data)
    assert not file.writable
    MoonrakerDriver(file)
    await bench.close()


# ---------------------------------------------------------------------- WebSocket


async def test_websocket_subscribes_and_follows_updates(ws_sim: MoonrakerSim) -> None:
    bench = await ws_bench(ws_sim).connect()
    driver = bench.driver
    assert isinstance(driver, MoonrakerDriver)
    assert "printer.objects.subscribe" not in ws_sim.calls
    assert "extruder" in driver.cache
    calls = len(ws_sim.calls)
    assert (await bench.read("state")).value == "standby"
    assert len(ws_sim.calls) == calls
    ws_sim.state.objects["print_stats"]["state"] = "printing"
    await ws_sim.notify()
    await eventually(lambda: _state_is(bench, "printing"))
    assert_done(await bench.write("extruder_target", "190 degC"))
    assert ws_sim.state.objects["extruder"]["target"] == 190.0
    await ws_sim.notify()
    await eventually(lambda: _target_is(bench, 190.0))
    assert_failed(await bench.act("resume"), "not paused")
    await bench.close()


async def _state_is(bench: Bench, value: str) -> bool:
    return (await bench.read("state")).value == value


async def _target_is(bench: Bench, value: float) -> bool:
    return (await bench.read("extruder_target")).value == value


async def test_websocket_disconnect_and_reconnect(ws_sim: MoonrakerSim) -> None:
    bench = await ws_bench(ws_sim).connect()
    await ws_sim.drop_websockets()
    await eventually(lambda: _down(bench))
    with pytest.raises(DriverError, match="disconnected"):
        await bench.driver.read("extruder_temp")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert (await bench.read("state")).value == "standby"
    await bench.close()


async def _down(bench: Bench) -> bool:
    return not (await bench.driver.health()).connected


async def test_websocket_timeout_and_malformed(ws_sim: MoonrakerSim) -> None:
    bench = await ws_bench(ws_sim).connect()
    ws_sim.latency_s = 1.0
    with pytest.raises(TimeoutError, match=r"didn't answer printer\.gcode\.script"):
        await _gcode(bench)
    ws_sim.latency_s = 0.0
    ws_sim.malformed = True
    with pytest.raises(TimeoutError):
        await _gcode(bench)
    ws_sim.malformed = False
    assert_done(await bench.write("bed_target", "50 degC"))
    await bench.close()


async def _gcode(bench: Bench) -> None:
    driver = bench.driver
    assert isinstance(driver, MoonrakerDriver)
    await driver._gcode("M107")


async def test_websocket_refused() -> None:
    file = loads(text(1, extra=", transport: websocket"))
    with pytest.raises(DriverError, match="Could not open the Moonraker WebSocket"):
        await MoonrakerDriver(file).connect()


# ---------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { mystery: { unit: degC } }", "not a Moonraker channel"),
        ("read: { t: { unit: degC, map: { object: 'bad;obj', field: temperature } } }", "should match pattern"),
        ("read: { t: { type: image } }", "images"),
        ("write: { w: { unit: degC, min: 0, max: 1, map: { heater: a, fan: b } } }", "exactly one"),
        ("write: { w: { unit: degC, min: 0, max: 1, map: { heater: 'x HEATER=y' } } }", "should match pattern"),
        ("write: { fan_speed: { unit: dimensionless, min: 0, max: 1 } }", "percent"),
        ("write: { extruder_target: { unit: V, min: 0, max: 1 } }", "degC"),
        ("write: { extruder_target: { type: bool } }", "numbers"),
        ("actions: { home: { args: { speed: { unit: mm/s, min: 0, max: 1 } } } }", "only an axes"),
        ("actions: { dance: {} }", "not a Moonraker channel"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MoonrakerDriver(loads(f"device: Bad\nconnect: {{ moonraker: x.local }}\n{snippet}\n"))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("token_env: lower", "should match pattern"),
        ("timeout: 5", "needs a unit"),
        ("action_wait: 30 s", "between"),
        ("transport: carrier_pigeon", "Input should be"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(Exception, match=message):
        MoonrakerDriver(loads(f"device: Bad\nconnect: {{ moonraker: x.local, {params} }}\n"))
