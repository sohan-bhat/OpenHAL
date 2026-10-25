"""The INDI driver, against the simulated INDI server on a local TCP port."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.indi.driver import IndiDriver
from openhal.drivers.indi.simulator import IndiServerSim
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

MOUNT = """
device: Test mount
id: mount
connect: {{ indi: 127.0.0.1, port: {port}, device: Telescope Simulator, timeout: 500 ms, action_wait: 2 s }}
read:
  right_ascension: {{ unit: deg }}
  declination: {{ unit: deg, range: [-90, 90] }}
  altitude: {{ unit: deg }}
  azimuth: {{ unit: rad }}
  slewing: {{ type: bool }}
  coord_state: {{ type: enum, values: [idle, ok, busy, alert], map: {{ property: EQUATORIAL_EOD_COORD, state: true }} }}
  parked: {{ type: bool }}
  on_set: {{ type: enum, values: [track, slew, sync], map: {{ property: ON_COORD_SET }} }}
write:
  tracking: {{ type: bool }}
actions:
  slew_to_coordinates:
    args: {{ right_ascension: {{ unit: deg, min: 0, max: 359.99 }}, declination: {{ unit: deg, min: -30, max: 90 }} }}
  abort: {{}}
  park: {{}}
  unpark: {{}}
safe_state: {{ tracking: false }}
hazard: medium
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture
async def server() -> AsyncIterator[IndiServerSim]:
    sim = IndiServerSim()
    sim.time_scale = 20
    await sim.start()
    yield sim
    await sim.stop()


def make(sim: IndiServerSim, text: str = MOUNT) -> tuple[IndiDriver, Bench]:
    file = loads(text.format(port=sim.port))
    driver = IndiDriver(file)
    return driver, Bench(file, driver)


async def test_connect_turns_the_device_on_and_waits_for_its_properties(server: IndiServerSim) -> None:
    driver, bench = make(server)
    await bench.connect()
    assert server.telescope.connected
    assert "CONNECTION" in server.received_names("newSwitchVector")
    gets = [item.get("device") for item in server.received if item.tag == "getProperties"]
    assert gets == ["Telescope Simulator"]
    identity = await driver.identify()
    assert identity["driver_exec"] == "indi_simulator_telescope"
    assert identity["driver_interface"] == "5"
    assert (await driver.health()).connected
    await bench.close()
    assert server.telescope.connected


async def test_reads_convert_hours_angles_switches_and_states(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    assert (await bench.read("right_ascension")).value == pytest.approx(82.5)
    assert (await bench.read("declination")).value == pytest.approx(22.0)
    reading = await bench.read("azimuth")
    assert (reading.value, reading.unit) == (pytest.approx(3.14159265), "rad")
    assert (await bench.read("slewing")).value is False
    assert (await bench.read("coord_state")).value == "idle"
    assert (await bench.read("parked")).value is False
    assert (await bench.read("on_set")).value == "track"
    assert (await bench.read("tracking")).value is False
    await bench.close()


async def test_tracking_uses_the_off_member(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    assert_done(await bench.write("tracking", True))
    assert server.telescope.extra["TELESCOPE_TRACK_STATE"].members == {"TRACK_ON": True, "TRACK_OFF": False}
    assert_done(await bench.write("tracking", False))
    assert server.telescope.extra["TELESCOPE_TRACK_STATE"].members == {"TRACK_ON": False, "TRACK_OFF": True}
    await bench.close()


async def test_slew_sets_the_coordinate_mode_then_follows_the_busy_state(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    decision = await bench.act("slew_to_coordinates", right_ascension="90 deg", declination="45 deg")
    assert_done(decision)
    names = server.received_names("newSwitchVector")
    assert names[-1] == "ON_COORD_SET"
    coords = server.telescope.extra["EQUATORIAL_EOD_COORD"]
    assert coords.members == {"RA": pytest.approx(6.0), "DEC": pytest.approx(45.0)}
    assert coords.state == "Ok"
    assert (await bench.read("tracking")).value is True
    await bench.close()


async def test_slow_slew_returns_started_and_abort_stops_it(server: IndiServerSim) -> None:
    text = MOUNT.replace("action_wait: 2 s", "action_wait: 300 ms")
    _driver, bench = make(server, text)
    await bench.connect()
    server.telescope.slew_s = 100
    assert_done(await bench.act("slew_to_coordinates", right_ascension="30 deg", declination="10 deg"))
    assert (await bench.read("slewing")).value is True
    assert_done(await bench.act("abort"))
    await eventually(lambda: _value(bench, "coord_state", "alert"))
    assert (await bench.read("slewing")).value is False
    await bench.close()


async def _value(bench: Bench, channel: str, wanted: object) -> bool:
    return (await bench.read(channel)).value == wanted


async def test_alert_answers_fail_with_the_device_message(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    assert_done(await bench.act("park"))
    assert (await bench.read("parked")).value is True
    decision = await bench.act("slew_to_coordinates", right_ascension="30 deg", declination="10 deg")
    assert_failed(decision, "Mount is parked")
    assert_done(await bench.act("unpark"))
    await bench.close()


async def test_stop_sends_abort_then_the_file_steps(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    assert_done(await bench.write("tracking", True))
    assert await bench.stop() == "safe"
    names = server.received_names("newSwitchVector")
    assert names[-2:] == ["TELESCOPE_ABORT_MOTION", "TELESCOPE_TRACK_STATE"]
    assert server.telescope.extra["TELESCOPE_TRACK_STATE"].members["TRACK_ON"] is False
    await bench.close()


FOCUSER = """
device: Test focuser
id: focuser
connect: {{ indi: 127.0.0.1, port: {port}, device: Focuser Simulator, kind: focuser, timeout: 500 ms }}
read:
  moving: {{ type: bool }}
  temperature: {{ unit: degC }}
write:
  position: {{ unit: dimensionless, min: 0, max: 50000 }}
actions:
  abort: {{}}
hazard: low
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


async def test_focuser_moves_and_aborts(server: IndiServerSim) -> None:
    _driver, bench = make(server, FOCUSER)
    await bench.connect()
    assert (await bench.read("temperature")).value == 12.5
    server.focuser.speed = 10.0
    assert_done(await bench.write("position", "20000 dimensionless"))
    assert (await bench.read("moving")).value is True
    assert await bench.stop() == "safe"
    assert server.received_names("newSwitchVector")[-1] == "FOCUS_ABORT_MOTION"
    await eventually(lambda: _value(bench, "moving", False))
    server.focuser.speed = 1e9
    assert_done(await bench.write("position", "15000 dimensionless"))
    await eventually(lambda: _value(bench, "position", 15000.0))
    await bench.close()


CAMERA = """
device: Test camera
id: camera
connect: {{ indi: 127.0.0.1, port: {port}, device: CCD Simulator, kind: camera, timeout: 500 ms }}
read:
  ccd_temperature: {{ unit: degC }}
  exposing: {{ type: bool }}
  exposure_left: {{ unit: s }}
write:
  cooler: {{ type: bool }}
  target_temperature: {{ unit: degC, min: -20, max: 20 }}
actions:
  start_exposure: {{ args: {{ duration: {{ unit: ms, min: 1, max: 600000 }} }} }}
  abort_exposure: {{}}
hazard: low
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


async def test_camera_cooling_and_exposure(server: IndiServerSim) -> None:
    _driver, bench = make(server, CAMERA)
    await bench.connect()
    assert_done(await bench.write("target_temperature", "10 degC"))
    assert (await bench.read("cooler")).value is True
    await eventually(lambda: _value(bench, "ccd_temperature", 10.0), within=3)
    server.time_scale = 1
    assert_done(await bench.act("start_exposure", duration="60000 ms"))
    assert server.camera.extra["CCD_EXPOSURE"].members["CCD_EXPOSURE_VALUE"] == pytest.approx(60.0, abs=1)
    assert (await bench.read("exposing")).value is True
    assert await bench.stop() == "safe"
    await eventually(lambda: _value(bench, "exposing", False))
    assert_done(await bench.write("cooler", False))
    await bench.close()


async def test_refused_writes_never_go_out(server: IndiServerSim) -> None:
    text = MOUNT.replace(
        "  tracking: {{ type: bool }}\n",
        "  tracking: {{ type: bool }}\n"
        "  horizon: {{ unit: deg, min: 0, max: 90, map: {{ property: HORIZONTAL_COORD, element: ALT }} }}\n"
        "  mode: {{ type: bool, map: {{ property: ON_COORD_SET, element: SLEW }} }}\n"
        "  bogus: {{ type: bool, map: {{ property: ON_COORD_SET, element: NOPE }} }}\n",
    )
    _driver, bench = make(server, text)
    await bench.connect()
    sent = len(server.received)
    assert_failed(await bench.write("horizon", "10 deg"), "read only")
    assert_failed(await bench.write("mode", False), "needs map.off")
    assert_failed(await bench.write("bogus", True), "has no member NOPE")
    assert len(server.received) == sent
    await bench.close()


async def test_connect_failures(server: IndiServerSim) -> None:
    driver, bench = make(server, MOUNT.replace("Telescope Simulator", "Dome Simulator"))
    with pytest.raises(DriverError, match="has no device 'Dome Simulator'"):
        await bench.connect()
    await bench.close()
    server.refuse_connect = True
    driver, bench = make(server)
    with pytest.raises(DriverError, match="Cannot open the serial port"):
        await bench.connect()
    await bench.close()
    server.refuse_connect = False
    text = MOUNT.replace(
        "  parked: {{ type: bool }}\n", "  parked: {{ type: bool, map: {{ property: MISSING, element: X }} }}\n"
    )
    driver, bench = make(server, text.replace("action_wait: 2 s", "action_wait: 2 s, define_wait: 300 ms"))
    with pytest.raises(DriverError, match=r"never defined Telescope Simulator\.MISSING"):
        await bench.connect()
    await bench.close()
    driver, _ = make(server)
    driver.settings = driver.settings.model_copy(update={"port": 9})
    with pytest.raises(DriverError, match="Could not reach the INDI server"):
        await driver.connect()


async def test_connect_device_false_uses_an_already_connected_device(server: IndiServerSim) -> None:
    server.telescope.connected = True
    text = MOUNT.replace("action_wait: 2 s", "action_wait: 2 s, connect_device: false")
    _driver, bench = make(server, text)
    await bench.connect()
    assert "CONNECTION" not in server.received_names("newSwitchVector")
    assert (await bench.read("declination")).value == 22.0
    await bench.close()


async def test_silent_server_times_out_changes(server: IndiServerSim) -> None:
    _driver, bench = make(server)
    await bench.connect()
    server.silent = True
    assert_failed(await bench.write("tracking", True), "didn't answer")
    server.silent = False
    await bench.close()


async def test_dropped_connection_and_reconnect(server: IndiServerSim) -> None:
    driver, bench = make(server)
    await bench.connect()
    server.drop_clients()
    await eventually(lambda: _disconnected(driver))
    assert "closed the connection" in (await driver.health()).detail
    with pytest.raises(DriverError, match="connection was lost"):
        await driver.read("declination")
    await bench.connect()
    assert (await bench.read("declination")).value == 22.0
    await bench.close()


async def _disconnected(driver: IndiDriver) -> bool:
    return not (await driver.health()).connected


@pytest.mark.parametrize(
    ("data", "reason"),
    [(b"<setNumberVector device='x'></broken>", "bad XML"), (b'<!DOCTYPE lol [<!ENTITY a "a">]>', "document type")],
)
async def test_bad_xml_drops_the_connection(server: IndiServerSim, data: bytes, reason: str) -> None:
    driver, bench = make(server)
    await bench.connect()
    server.inject(data)
    await eventually(lambda: _disconnected(driver))
    assert reason in (await driver.health()).detail
    await bench.close()


async def test_unreadable_update_marks_the_property_until_a_good_one(server: IndiServerSim) -> None:
    driver, bench = make(server)
    await bench.connect()
    server.inject(
        b'<setNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD" state="Ok">'
        b'<oneNumber name="DEC">north</oneNumber></setNumberVector>'
    )
    assert driver.session is not None
    coords = driver.session.vectors[("Telescope Simulator", "EQUATORIAL_EOD_COORD")]
    await eventually(lambda: asyncio.sleep(0, bool(coords.invalid)))
    with pytest.raises(DriverError, match="can't read"):
        await driver.read("declination")
    server.inject(
        b'<setNumberVector device="Telescope Simulator" name="EQUATORIAL_EOD_COORD" state="Ok">'
        b'<oneNumber name="DEC">10</oneNumber></setNumberVector>'
    )
    await eventually(lambda: asyncio.sleep(0, not coords.invalid))
    assert (await bench.read("declination")).value == 10.0
    await bench.close()


async def test_device_removed_by_the_server(server: IndiServerSim) -> None:
    driver, bench = make(server)
    await bench.connect()
    server.inject(b'<delProperty device="Telescope Simulator"/>')
    await eventually(lambda: _disconnected(driver))
    assert "removed" in (await driver.health()).detail
    await bench.close()


async def test_describe_proposes_suggested_entries(server: IndiServerSim) -> None:
    for text, write, action in (
        (MOUNT, "tracking", "slew_to_coordinates"),
        (FOCUSER, "position", "abort"),
        (CAMERA, "target_temperature", "start_exposure"),
    ):
        driver, bench = make(server, text)
        await bench.connect()
        proposal = await driver.describe()
        assert proposal is not None
        assert proposal["write"][write]["suggested"] is True
        assert all(entry["suggested"] for entry in proposal["actions"].values())
        assert action in proposal["actions"]
        await bench.close()
    driver, _ = make(server)
    assert await driver.describe() is None
    focuser, bench = make(server, FOCUSER)
    await bench.connect()
    proposal = await focuser.describe()
    assert proposal is not None
    assert proposal["write"]["position"]["max"] == 100000.0
    await bench.close()


async def test_discovery_lists_devices_without_connecting_them(
    server: IndiServerSim, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(IndiDriver, "discovery_hosts", [("127.0.0.1", server.port), ("127.0.0.1", 9)])
    monkeypatch.setattr(IndiDriver, "discovery_wait", 0.2)
    found = await IndiDriver.discover()
    names = {item.label for item in found}
    assert names == {"Telescope Simulator", "Focuser Simulator", "CCD Simulator"}
    mount = next(item for item in found if item.label == "Telescope Simulator")
    assert mount.address == f"indi://127.0.0.1:{server.port}/Telescope Simulator"
    assert mount.identifiers["indi.driver"] == "Telescope Simulator"
    assert not any(item.tag.startswith("new") for item in server.received)
    assert not server.telescope.connected


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { colour: { type: string } }", "not an INDI property"),
        ("read: { frame: { type: image } }", "doesn't download images"),
        ("read: { busy: { unit: deg, map: { property: P, state: true } } }", "bool \\(busy\\) or an enum"),
        ("read: { busy: { type: enum, values: [idle, maybe], map: { property: P, state: true } } }", "states are"),
        ("read: { both: { type: bool, map: { property: P, element: E, state: true } } }", "element or state"),
        ("write: { speed: { unit: deg, min: 0, max: 1, map: { property: P } } }", "give map.element"),
        ("actions: { abort: { args: { x: { unit: deg, min: 0, max: 1 } } } }", "must match"),
        ("actions: { go: { map: { property: P } } }", "not both"),
        ("actions: { dance: {} }", "not an INDI property"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ indi: localhost, device: Telescope Simulator }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        IndiDriver(loads(text))


@pytest.mark.parametrize(("params", "message"), [("timeout: 0 s", "timeout"), ("action_wait: 30 s", "action_wait")])
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        IndiDriver(loads(f"device: Bad\nid: bad\nconnect: {{ indi: localhost, device: X, {params} }}\n"))


async def test_waiting_for_a_condition_times_out_cleanly(server: IndiServerSim) -> None:
    driver, bench = make(server)
    await bench.connect()
    assert driver.session is not None
    assert await driver.session.wait_for(lambda: False, 0.05) is False
    await asyncio.sleep(0)
    await bench.close()


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/indi/examples/eq6-mount.hal.yaml")
    assert not file.writable
    driver = IndiDriver(file)
    assert {"abort", "park", "slew_to_coordinates"} <= set(driver.actions)
