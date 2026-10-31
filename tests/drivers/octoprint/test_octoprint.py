"""The OctoPrint driver, against the simulated REST API."""

from __future__ import annotations

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.octoprint.driver import OctoPrintDriver, state_from_flags
from openhal.drivers.octoprint.simulator import OctoPrintSim
from openhal.spec import loads
from openhal.spec.loader import from_data
from tests.drivers.serial.kit import Bench, assert_done, assert_failed

PRINTER = """
device: MK3S
id: mk3s
connect: { octoprint: octopi.local, token_env: OCTO_TEST_KEY, timeout: 300 ms }
read:
  state: { type: enum, values: [standby, printing, paused, cancelling, error, offline] }
  state_text: { type: string }
  extruder_temp: { unit: degC }
  tool1_temp: { unit: degC, map: { heater: tool1 } }
  bed_temp: { unit: degF }
  chamber_temp: { unit: degC }
  bed_target_seen: { unit: degC, map: { heater: bed, field: target } }
  progress: { unit: percent }
  filename: { type: string }
write:
  extruder_target: { unit: degC, min: 0, max: 260 }
  tool1_target: { unit: degC, min: 0, max: 260, map: { heater: tool1 } }
  bed_target: { unit: degF, min: 32, max: 230 }
  chamber_target: { unit: degC, min: 0, max: 60 }
  fan_speed: { unit: percent, min: 0, max: 100 }
actions:
  home: { args: { axes: { type: enum, values: [x, y, z, xy, all] } } }
  pause: {}
  resume: {}
  cancel: {}
safe_state:
  - { fan_speed: 0 }
hazard: medium
confirmed: { by: tester, at: 2026-10-24 }
"""


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCTO_TEST_KEY", "octo-key")


def make(sim: OctoPrintSim, text: str = PRINTER) -> Bench:
    file = loads(text)
    return Bench(file, OctoPrintDriver(file, http_transport=sim.http_transport()))


async def test_reads() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    assert (await bench.read("state")).value == "standby"
    assert (await bench.read("state_text")).value == "Operational"
    assert (await bench.read("extruder_temp")).value == pytest.approx(22.0, abs=0.5)
    assert (await bench.read("tool1_temp")).value == pytest.approx(22.5, abs=0.5)
    bed = await bench.read("bed_temp")
    assert bed.unit == "degF"
    assert bed.value == pytest.approx(70.0, abs=1.5)
    assert (await bench.read("chamber_temp")).value == pytest.approx(24.0, abs=0.5)
    assert (await bench.read("progress")).value is None
    sim.job_state, sim.completion, sim.filename = "printing", 12.5, "benchy.gcode"
    assert (await bench.read("state")).value == "printing"
    assert (await bench.read("progress")).value == 12.5
    assert (await bench.read("filename")).value == "benchy.gcode"
    identity = await bench.driver.identify()
    assert identity["server"] == "1.10.2"
    assert (await bench.driver.health()).detail == "OctoPrint 1.10.2"
    await bench.close()


async def test_writes() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    assert_done(await bench.write("extruder_target", "215 degC"))
    assert sim.temps["tool0"]["target"] == 215.0
    assert_done(await bench.write("tool1_target", "190 degC"))
    assert sim.temps["tool1"]["target"] == 190.0
    assert_done(await bench.write("bed_target", "140 degF"))
    assert sim.temps["bed"]["target"] == pytest.approx(60.0)
    assert (await bench.read("bed_target")).value == pytest.approx(140.0)
    assert (await bench.read("bed_target_seen")).value == pytest.approx(60.0)
    assert_done(await bench.write("chamber_target", "35 degC"))
    assert sim.temps["chamber"]["target"] == 35.0
    assert (await bench.read("fan_speed")).value is None
    assert_done(await bench.write("fan_speed", "100 %"))
    assert sim.commands == ["M106 P0 S255"]
    assert (await bench.read("fan_speed")).value == 100.0
    await bench.close()


async def test_actions_and_conflicts() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    assert_done(await bench.act("home", axes="xy"))
    assert sim.homed == [["x", "y"]]
    assert_failed(await bench.act("pause"), "not printing")
    sim.job_state = "printing"
    assert_failed(await bench.act("home", axes="all"), "currently printing")
    assert_done(await bench.act("pause"))
    assert (await bench.read("state")).value == "paused"
    assert_done(await bench.act("resume"))
    assert_done(await bench.act("cancel"))
    assert sim.job_state == "idle"
    await bench.close()


async def test_native_safe_state() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    for channel, value in (
        ("extruder_target", "200 degC"),
        ("tool1_target", "200 degC"),
        ("chamber_target", "30 degC"),
    ):
        assert_done(await bench.write(channel, value))
    assert_done(await bench.write("fan_speed", "40 %"))
    assert await bench.stop() == "safe"
    assert all(heater["target"] == 0 for heater in sim.temps.values())
    assert sim.commands[-1] == "M106 P0 S0"
    await bench.close()


async def test_offline_printer() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    sim.offline()
    health = await bench.driver.health()
    assert not health.connected
    assert "can't do this now" in health.detail
    assert (await bench.read("state")).value == "offline"
    with pytest.raises(DriverError, match="not operational"):
        await bench.driver.read("extruder_temp")
    assert_failed(await bench.write("extruder_target", "10 degC"), "not operational")
    await bench.close()


async def test_api_key_problems(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = OctoPrintSim()
    bench = make(sim)
    monkeypatch.delenv("OCTO_TEST_KEY")
    with pytest.raises(DriverError, match="Set the OCTO_TEST_KEY"):
        await bench.driver.connect()
    monkeypatch.setenv("OCTO_TEST_KEY", "wrong")
    with pytest.raises(DriverError, match="did not accept the API key"):
        await bench.driver.connect()
    await bench.close()


async def test_transport_faults() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    sim.latency_s = 1.0
    with pytest.raises(TimeoutError, match="sent no reply"):
        await bench.driver.read("extruder_temp")
    sim.latency_s = 0.0
    sim.malformed = True
    with pytest.raises(DriverError, match="not JSON"):
        await bench.driver.read("extruder_temp")
    sim.malformed = False
    sim.fail_http = True
    with pytest.raises(DriverError, match="Could not reach OctoPrint"):
        await bench.driver.read("extruder_temp")
    assert not (await bench.driver.health()).connected
    sim.fail_http = False
    del sim.temps["chamber"]
    with pytest.raises(DriverError, match="reports no actual for chamber"):
        await bench.driver.read("chamber_temp")
    await bench.close()


async def test_not_connected() -> None:
    driver = OctoPrintDriver(loads(PRINTER))
    assert await driver.identify() == {"host": "octopi.local"}
    assert await driver.describe() is None
    assert not (await driver.health()).connected
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("fan_speed")


async def test_describe_from_the_printer_profile() -> None:
    sim = OctoPrintSim()
    bench = await make(sim).connect()
    proposal = await bench.driver.describe()
    assert proposal is not None
    assert proposal["device"]["name"] == "Prusa i3 MK3S"
    assert set(proposal["write"]) == {
        "extruder_target",
        "extruder1_target",
        "bed_target",
        "chamber_target",
        "fan_speed",
    }
    assert all(entry["suggested"] for entry in proposal["write"].values())
    file = from_data({**proposal, "connect": {"octoprint": "octopi.local"}})
    assert not file.writable
    OctoPrintDriver(file)
    await bench.close()


@pytest.mark.parametrize(
    ("flags", "state"),
    [
        ({"closedOrError": True, "error": True}, "error"),
        ({"closedOrError": True}, "offline"),
        ({"operational": True, "cancelling": True, "printing": True}, "cancelling"),
        ({"operational": True, "pausing": True}, "paused"),
        ({"operational": True, "printing": True}, "printing"),
        ({"operational": True, "ready": True}, "standby"),
    ],
)
def test_state_from_flags(flags: dict[str, bool], state: str) -> None:
    assert state_from_flags(flags) == state


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { mystery: { unit: degC } }", "not an OctoPrint channel"),
        ("read: { state: { type: enum, values: [standby, exploding] } }", "values from"),
        ("read: { t: { unit: degC, map: { heater: tool99 } } }", "should match pattern"),
        ("read: { t: { type: string, map: { heater: bed } } }", "numbers"),
        ("write: { fan_speed: { unit: dimensionless, min: 0, max: 255 } }", "percent"),
        ("write: { bed_target: { unit: V, min: 0, max: 1 } }", "degC"),
        ("write: { w: { unit: degC, min: 0, max: 1, map: { heater: bed, fan: 0 } } }", "exactly one"),
        ("actions: { home: { args: { feed: { unit: mm/s, min: 0, max: 1 } } } }", "only an axes"),
        ("actions: { dance: {} }", "not an OctoPrint channel"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        OctoPrintDriver(loads(f"device: Bad\nconnect: {{ octoprint: x.local }}\n{snippet}\n"))


@pytest.mark.parametrize(
    ("params", "message"),
    [("path: 'no slash'", "should match pattern"), ("timeout: 9", "needs a unit"), ("token_env: x", "pattern")],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(Exception, match=message):
        OctoPrintDriver(loads(f"device: Bad\nconnect: {{ octoprint: x.local, {params} }}\n"))
