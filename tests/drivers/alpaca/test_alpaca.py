"""The Alpaca driver, against the simulated Alpaca server on an httpx mock transport."""

from __future__ import annotations

from pathlib import Path

import pytest

from openhal.drivers.alpaca.client import AlpacaClient, error_name, form
from openhal.drivers.alpaca.driver import AlpacaDriver
from openhal.drivers.alpaca.simulator import AlpacaSim, DiscoveryResponder
from openhal.drivers.base import DriverError
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed

MOUNT = """
device: Test mount
id: mount
connect: { alpaca: sim.local, device_type: telescope, timeout: 500 ms, action_wait: 2 s }
read:
  right_ascension: { unit: deg }
  declination: { unit: deg, range: [-90, 90] }
  altitude: { unit: deg }
  azimuth: { unit: rad }
  sidereal_time: { unit: deg }
  slewing: { type: bool }
  at_park: { type: bool }
  dome_shutter:
    type: enum
    values: [open, closed, opening, closing, error]
    map: { device: dome, property: shutterstatus, states: [open, closed, opening, closing, error] }
write:
  tracking: { type: bool }
actions:
  slew_to_coordinates:
    args: { right_ascension: { unit: deg, min: 0, max: 359.99 }, declination: { unit: deg, min: -30, max: 90 } }
  slew_to_alt_az:
    args: { azimuth: { unit: deg, min: 0, max: 359.99 }, altitude: { unit: deg, min: 10, max: 90 } }
  abort_slew: {}
  park: {}
  unpark: {}
  find_home: {}
  open_dome: { map: { device: dome, method: openshutter } }
safe_state: { tracking: false }
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""


def make(text: str = MOUNT, sim: AlpacaSim | None = None) -> tuple[AlpacaDriver, AlpacaSim, Bench]:
    server = sim or AlpacaSim()
    server.time_scale = 20
    file = loads(text)
    driver = AlpacaDriver(file, http_transport=server.http_transport())
    return driver, server, Bench(file, driver)


async def test_connect_checks_the_server_and_connects_every_device_used() -> None:
    driver, sim, bench = make()
    await bench.connect()
    paths = [path for _, path, _ in sim.requests]
    assert paths[:3] == ["/management/apiversions", "/management/v1/description", "/management/v1/configureddevices"]
    assert sim.telescope.connected
    assert sim.dome.connected
    assert not sim.focuser.connected
    connect = sim.puts("connected")[0]
    assert connect["Connected"] == "True"
    assert {"ClientID", "ClientTransactionID"} <= set(connect)
    identity = await driver.identify()
    assert identity["name"] == "Sim Mount"
    assert identity["interfaceversion"] == "3"
    assert identity["server_name"] == "OpenHAL Alpaca simulator"
    assert (await driver.health()).connected
    await bench.close()
    assert sim.telescope.connected


async def test_mount_reads_convert_hours_and_angles() -> None:
    _driver, _, bench = make()
    await bench.connect()
    assert (await bench.read("right_ascension")).value == pytest.approx(82.5)
    assert (await bench.read("declination")).value == pytest.approx(22.0)
    reading = await bench.read("azimuth")
    assert (reading.value, reading.unit) == (pytest.approx(3.14159265), "rad")
    assert (await bench.read("sidereal_time")).value == pytest.approx(93.75)
    assert (await bench.read("slewing")).value is False
    assert (await bench.read("dome_shutter")).value == "closed"
    await bench.close()


async def test_suspect_reading_outside_the_range() -> None:
    _driver, sim, bench = make()
    await bench.connect()
    sim.telescope.dec = 120.0
    reading = await bench.read("declination")
    assert reading.suspect
    await bench.close()


async def test_tracking_write_and_slew_to_coordinates() -> None:
    _driver, sim, bench = make()
    await bench.connect()
    assert_done(await bench.write("tracking", True))
    assert sim.puts("tracking")[-1]["Tracking"] == "True"
    assert (await bench.read("tracking")).value is True
    decision = await bench.act("slew_to_coordinates", right_ascension="90 deg", declination="45 deg")
    assert_done(decision)
    sent = sim.puts("slewtocoordinatesasync")[-1]
    assert float(sent["RightAscension"]) == pytest.approx(6.0)
    assert float(sent["Declination"]) == pytest.approx(45.0)
    assert sim.telescope.ra == pytest.approx(6.0)
    await bench.close()


async def test_slow_slew_returns_started() -> None:
    text = MOUNT.replace("action_wait: 2 s", "action_wait: 200 ms")
    _driver, sim, bench = make(text)
    await bench.connect()
    sim.time_scale = 1
    sim.telescope.slew_s = 50
    assert_done(await bench.act("slew_to_alt_az", azimuth="120 deg", altitude="30 deg"))
    assert (await bench.read("slewing")).value is True
    assert_done(await bench.act("abort_slew"))
    assert (await bench.read("slewing")).value is False
    await bench.close()


async def test_device_refusals_become_failures_with_the_ascom_reason() -> None:
    _driver, sim, bench = make()
    await bench.connect()
    assert_failed(await bench.act("slew_to_coordinates", right_ascension="10 deg", declination="10 deg"), "0x40B")
    assert_done(await bench.act("park"))
    assert sim.telescope.parked
    decision = await bench.act("slew_to_alt_az", azimuth="10 deg", altitude="20 deg")
    assert_failed(decision, "0x408")
    assert "not allowed while parked" in decision.message
    assert_done(await bench.act("unpark"))
    assert_done(await bench.act("find_home"))
    assert sim.telescope.home
    await bench.close()


async def test_native_safe_state_aborts_and_a_parked_mount_counts_as_safe() -> None:
    _driver, sim, bench = make()
    await bench.connect()
    assert await bench.stop() == "safe"
    aborted = [path for method, path, _ in sim.requests if method == "PUT" and path.endswith("/abortslew")]
    assert aborted == ["/api/v1/dome/0/abortslew", "/api/v1/telescope/0/abortslew"]
    assert sim.puts("tracking")[-1]["Tracking"] == "False"
    sim.telescope.parked = True
    assert await bench.stop() == "safe"
    assert len(sim.puts("abortslew")) == 4
    await bench.close()


async def test_park_on_stop_parks_after_the_abort() -> None:
    text = MOUNT.replace("action_wait: 2 s", "action_wait: 2 s, park_on_stop: true").replace(
        "safe_state: { tracking: false }\n", ""
    )
    _driver, sim, bench = make(text)
    await bench.connect()
    assert await bench.stop() == "safe"
    methods = [path.rsplit("/", 1)[-1] for method, path, _ in sim.requests if method == "PUT"]
    assert methods[-2:] == ["abortslew", "park"]
    assert len([item for item in methods if item == "abortslew"]) == 2
    await bench.close()


async def test_action_on_another_device_of_the_server() -> None:
    _driver, sim, bench = make()
    await bench.connect()
    assert_done(await bench.act("open_dome"))
    assert sim.dome.shutter in (0, 2)
    await bench.close()


FOCUSER = """
device: Test focuser
id: focuser
connect: { alpaca: sim.local, device_type: focuser, timeout: 500 ms }
read:
  is_moving: { type: bool }
  temperature: { unit: degF }
  max_step: { unit: dimensionless }
write:
  position: { unit: dimensionless, min: 0, max: 40000 }
actions:
  halt: {}
safe_state: []
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_focuser_moves_in_whole_steps() -> None:
    _driver, sim, bench = make(FOCUSER)
    await bench.connect()
    assert (await bench.read("temperature")).value == pytest.approx(54.5)
    assert (await bench.read("max_step")).value == 50000
    assert_done(await bench.write("position", "12000 dimensionless"))
    assert sim.puts("move")[-1]["Position"] == "12000"
    assert_failed(await bench.write("position", "12000.5 dimensionless"), "not a whole number")
    assert len(sim.puts("move")) == 1
    assert_done(await bench.act("halt"))
    assert await bench.stop() == "safe"
    assert len(sim.puts("halt")) == 2
    await bench.close()


CAMERA = """
device: Test camera
id: camera
connect: { alpaca: sim.local, device_type: camera, timeout: 500 ms }
read:
  ccd_temperature: { unit: degC }
  camera_state: { type: enum, values: [idle, waiting, exposing, reading, download, error] }
  image_ready: { type: bool }
  percent_completed: { unit: percent }
write:
  cooler: { type: bool }
  target_temperature: { unit: degC, min: -20, max: 20 }
  gain: { unit: dimensionless, min: 0, max: 300, step: 1 }
actions:
  start_exposure: { args: { duration: { unit: ms, min: 1, max: 600000 }, light: { type: bool } } }
  abort_exposure: {}
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_camera_cooling_gain_and_exposure() -> None:
    _driver, sim, bench = make(CAMERA)
    await bench.connect()
    assert_done(await bench.write("cooler", True))
    assert_done(await bench.write("target_temperature", "-10 degC"))
    assert (await bench.read("ccd_temperature")).value == -10.0
    assert_done(await bench.write("gain", "120 dimensionless"))
    assert sim.puts("gain")[-1]["Gain"] == "120"
    sim.time_scale = 1
    assert_done(await bench.act("start_exposure", duration="30000 ms", light=True))
    sent = sim.puts("startexposure")[-1]
    assert (float(sent["Duration"]), sent["Light"]) == (30.0, "True")
    assert (await bench.read("camera_state")).value == "exposing"
    assert await bench.stop() == "safe"
    assert (await bench.read("camera_state")).value == "idle"
    assert sim.puts("abortexposure")
    await bench.close()


SWITCH = """
device: Test power box
id: power
connect: { alpaca: sim.local, device_type: switch, timeout: 500 ms }
read:
  switch_2: { unit: V }
write:
  switch_0: { type: bool }
  switch_1: { unit: percent, min: 0, max: 100, step: 1 }
safe_state: { switch_1: 0 }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_switches_by_id() -> None:
    _driver, sim, bench = make(SWITCH)
    await bench.connect()
    assert (await bench.read("switch_0")).value is True
    assert_done(await bench.write("switch_0", False))
    sent = sim.puts("setswitch")[-1]
    assert (sent["Id"], sent["State"]) == ("0", "False")
    assert_done(await bench.write("switch_1", "40 %"))
    assert sim.puts("setswitchvalue")[-1]["Value"] == "40.0"
    assert (await bench.read("switch_1")).value == 40.0
    assert (await bench.read("switch_2")).value == pytest.approx(12.3)
    assert await bench.stop() == "safe"
    assert sim.switch.switches[1]["value"] == 0.0
    await bench.close()


async def test_switch_describe_names_each_switch() -> None:
    driver, _sim, bench = make(SWITCH)
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["switch_0"] == {"type": "bool", "suggested": True}
    assert proposal["write"]["switch_1"]["max"] == 100.0
    assert proposal["read"]["switch_2"] == {"unit": "dimensionless", "range": [0.0, 20.0]}
    assert "switch_1 is Dew heater" in proposal["notes"]
    await bench.close()


DOME = """
device: Test dome
id: dome
connect: { alpaca: sim.local, device_type: dome, timeout: 500 ms, action_wait: 2 s }
read:
  azimuth: { unit: deg }
  shutter: { type: enum, values: [open, closed, opening, closing, error] }
actions:
  open_shutter: {}
  close_shutter: {}
  slew_to_azimuth: { args: { azimuth: { unit: deg, min: 0, max: 359 } } }
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""


async def test_dome_shutter_and_rotation() -> None:
    _driver, sim, bench = make(DOME)
    await bench.connect()
    sim.time_scale = 1
    sim.dome.move_s = 0.3
    assert (await bench.read("shutter")).value == "closed"
    assert_done(await bench.act("open_shutter"))
    assert (await bench.read("shutter")).value == "opening"
    assert_done(await bench.act("slew_to_azimuth", azimuth="200 deg"))
    assert (await bench.read("azimuth")).value == 200.0
    assert await bench.stop() == "safe"
    assert sim.puts("abortslew")
    await bench.close()


async def test_describe_proposes_suggested_entries_for_each_type() -> None:
    for text, write, action in (
        (MOUNT, "tracking", "park"),
        (FOCUSER, "position", "halt"),
        (CAMERA, "target_temperature", "start_exposure"),
        (DOME, None, "open_shutter"),
    ):
        driver, _, bench = make(text)
        await bench.connect()
        proposal = await driver.describe()
        assert proposal is not None
        if write:
            assert proposal["write"][write]["suggested"] is True
        assert proposal["actions"][action]["suggested"] is True
        assert all(entry.get("suggested") for entry in proposal["actions"].values())
        await bench.close()
    driver, _, _ = make()
    assert await driver.describe() is None


async def test_connect_refuses_a_device_the_server_does_not_offer() -> None:
    text = "device: Rotator\nid: rot\nconnect: { alpaca: sim.local, device_type: rotator }\n"
    _driver, _, bench = make(text + "read:\n  angle: { unit: deg, map: { property: position } }\n")
    with pytest.raises(DriverError, match="has no rotator 0"):
        await bench.connect()
    await bench.close()


async def test_server_faults_are_driver_errors() -> None:
    driver, sim, bench = make()
    await bench.connect()
    sim.malformed_next = 1
    with pytest.raises(DriverError, match="not JSON"):
        await driver.read("altitude")
    sim.server_error_next = 1
    with pytest.raises(DriverError, match="HTTP 500"):
        await driver.read("altitude")
    sim.fail_next = 1
    with pytest.raises(DriverError, match="Could not reach"):
        await driver.read("altitude")
    sim.latency_s = 1.0
    with pytest.raises(TimeoutError):
        await driver.read("altitude")
    sim.latency_s = 0.0
    sim.telescope.connected = False
    with pytest.raises(DriverError, match="0x407"):
        await driver.read("altitude")
    health = await driver.health()
    assert not health.connected
    await bench.connect()
    assert (await bench.read("altitude")).value == 45.0
    await bench.close()


async def test_bad_replies_from_the_client() -> None:
    import httpx

    def reply(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("missing"):
            return httpx.Response(200, json={"ErrorNumber": 0})
        if request.url.path.endswith("weird"):
            return httpx.Response(200, json={"ErrorNumber": "x", "Value": 1})
        if request.url.path.endswith("list"):
            return httpx.Response(200, json=[1, 2])
        if request.url.path.endswith("bad"):
            return httpx.Response(400, text="Id is missing")
        return httpx.Response(404, text="no")

    client = AlpacaClient("http://sim", timeout=1.0, transport=httpx.MockTransport(reply))
    with pytest.raises(DriverError, match="has no Value"):
        await client.get("/api/v1/telescope/0/missing")
    with pytest.raises(DriverError, match="ErrorNumber that is not a number"):
        await client.get("/api/v1/telescope/0/weird")
    with pytest.raises(DriverError, match="not a JSON object"):
        await client.get("/api/v1/telescope/0/list")
    with pytest.raises(DriverError, match="malformed"):
        await client.put("/api/v1/telescope/0/bad")
    with pytest.raises(DriverError, match="Check the device type"):
        await client.get("/api/v1/telescope/9/name")
    await client.close()
    assert error_name(0x500) == "a driver specific error"
    assert error_name(7) == "an unknown error"
    assert (form(True), form(False), form(1.5), form(3)) == ("True", "False", "1.5", "3")


async def test_close_leaves_devices_connected_unless_asked() -> None:
    text = MOUNT.replace("action_wait: 2 s", "action_wait: 2 s, disconnect_on_close: true")
    _driver, sim, bench = make(text)
    await bench.connect()
    await bench.close()
    assert not sim.telescope.connected
    assert not sim.dome.connected


async def test_discovery_finds_servers_and_lists_their_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = AlpacaSim()
    responder, port = await DiscoveryResponder.start(alpaca_port=11111)
    try:
        monkeypatch.setattr(AlpacaDriver, "discovery_targets", [("127.0.0.1", port)])
        monkeypatch.setattr(AlpacaDriver, "discovery_wait", 0.3)
        monkeypatch.setattr(AlpacaDriver, "discovery_transport", sim.http_transport())
        found = await AlpacaDriver.discover()
    finally:
        responder.close()
    assert responder.queries == 1
    addresses = {item.address for item in found}
    assert "http://127.0.0.1:11111/api/v1/telescope/0" in addresses
    mount = next(item for item in found if item.identifiers["alpaca.device_type"] == "telescope")
    assert mount.label == "Sim Mount"
    assert mount.identifiers["alpaca.unique_id"] == "sim-telescope-0"
    assert not any(method == "PUT" for method, _, _ in sim.requests)


async def test_discovery_with_no_answers_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(AlpacaDriver, "discovery_targets", [("127.0.0.1", 9)])
    monkeypatch.setattr(AlpacaDriver, "discovery_wait", 0.1)
    assert await AlpacaDriver.discover() == []


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { colour: { type: string } }", "not an Alpaca member"),
        ("read: { frame: { type: image } }", "doesn't download images"),
        (
            "read: { shutter: { type: enum, values: [open, ajar],"
            " map: { property: shutterstatus, states: [open, closed] } } }",
            "values must come from",
        ),
        ("read: { odd: { type: bool, map: { property: slewing, switch: 1 } } }", "exactly one of property or switch"),
        ("read: { odd: { type: bool, map: { device: toaster, property: on } } }", "unknown Alpaca device type"),
        ("write: { speed: { unit: deg, min: 0, max: 1, map: { property: rate } } }", "give param"),
        ("write: { speed: { unit: deg, min: 0, max: 1, map: { method: move, param: Position } } }", "needs readback"),
        (
            "write: { flag: { type: bool, map: { property: rate, param: Rate, integer: true } } }",
            "integer only applies",
        ),
        (
            "actions: { slew_to_coordinates: { args: { right_ascension: { unit: deg, min: 0, max: 1 } } } }",
            "needs the arguments",
        ),
        ("actions: { park: { args: { speed: { unit: deg, min: 0, max: 1 } } } }", "no Alpaca parameter"),
        ("actions: { dance: {} }", "not an Alpaca member"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ alpaca: sim.local }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        AlpacaDriver(loads(text))


@pytest.mark.parametrize(("params", "message"), [("timeout: 0 s", "timeout"), ("action_wait: 20 s", "action_wait")])
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        AlpacaDriver(loads(f"device: Bad\nid: bad\nconnect: {{ alpaca: sim.local, {params} }}\n"))


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/alpaca/examples/eq-mount.hal.yaml")
    assert not file.writable
    driver = AlpacaDriver(file)
    assert "abort_slew" in driver.actions
    assert "park" in driver.actions
