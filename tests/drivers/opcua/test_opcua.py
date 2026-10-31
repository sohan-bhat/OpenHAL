"""The OPC UA driver, against asyncua's own server running the simulated pump skid."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.opcua import channels, units
from openhal.drivers.opcua.driver import OpcuaDriver
from openhal.drivers.opcua.simulator import OpcuaSim, shared
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

NS = "nsu=urn:openhal:sim:pump;s="
SKID = f"""
device: Pump skid
id: pump
connect: {{{{ opcua: "{{endpoint}}", timeout: 600 ms }}}}
read:
  temperature: {{{{ unit: degF, map: {{{{ node: "{NS}Pump.Temperature" }}}} }}}}
  running: {{{{ type: bool, map: {{{{ node: "{NS}Pump.Running" }}}} }}}}
  tank_temperature: {{{{ unit: degC, map: {{{{ node: "{NS}Tank.TempF" }}}} }}}}
  level: {{{{ unit: percent, range: [10, 90], map: {{{{ node: "{NS}Tank.Level" }}}} }}}}
  pressure: {{{{ unit: bar, map: {{{{ node: "{NS}Tank.Pressure" }}}} }}}}
write:
  speed: {{{{ unit: rpm, min: 0, max: 2000, map: {{{{ node: "{NS}Pump.Speed" }}}} }}}}
  setpoint: {{{{ unit: percent, min: 0, max: 100, map: {{{{ node: "{NS}Pump.Setpoint" }}}} }}}}
  mode: {{{{ type: enum, values: [auto, manual], map: {{{{ node: "{NS}Pump.Mode" }}}} }}}}
actions:
  start:
    args: {{{{ rate: {{{{ unit: rpm, min: 0, max: 1000 }}}} }}}}
    map: {{{{ object: "{NS}Pump", method: "{NS}Pump.Start", inputs: [rate] }}}}
  stop: {{{{ map: {{{{ object: "{NS}Pump", method: "{NS}Pump.Stop" }}}} }}}}
  prime: {{{{ map: {{{{ object: "{NS}Pump", method: "{NS}Pump.Prime" }}}} }}}}
safe_state:
  - {{{{ action: stop }}}}
  - {{{{ speed: 0 }}}}
hazard: medium
confirmed: {{{{ by: tester, at: 2026-10-24 }}}}
"""


@pytest.fixture(scope="module")
def server() -> OpcuaSim:
    return shared()


@pytest.fixture
async def sim(server: OpcuaSim) -> AsyncIterator[OpcuaSim]:
    server.reset()
    return server


def make(sim: OpcuaSim, text: str = SKID) -> tuple[OpcuaDriver, Bench]:
    file = loads(text.format(endpoint=sim.endpoint))
    driver = OpcuaDriver(file)
    return driver, Bench(file, driver)


def _alter(old: str, new: str) -> str:
    assert old in SKID
    return SKID.replace(old, new)


async def test_connect_checks_every_node_and_identifies_the_server(sim: OpcuaSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    identity = await driver.identify()
    assert identity["product"] == "FreeOpcUa Python Server"
    assert identity["manufacturer"] == "FreeOpcUa"
    assert driver.variables["speed"].unit == "rpm"
    assert driver.variables["level"].span == (0.0, 100.0)
    assert (await driver.health()).connected
    await bench.close()
    assert not (await driver.health()).connected


async def test_reads_convert_engineering_units(sim: OpcuaSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert (await bench.read("temperature")).value == pytest.approx(70.7)
    assert (await bench.read("tank_temperature")).value == pytest.approx(21.111, abs=1e-3)
    assert (await bench.read("pressure")).value == pytest.approx(1.013)
    assert (await bench.read("running")).value is False
    assert (await bench.read("mode")).value == "auto"
    reading = await bench.read("level")
    assert (reading.value, reading.unit, reading.suspect) == (pytest.approx(64.0), "percent", False)
    sim.set("Tank.Level", _float(95.0))
    assert (await bench.read("level")).suspect
    await bench.close()


def _float(value: float) -> object:
    from asyncua import ua

    return ua.Variant(value, ua.VariantType.Float)


async def test_status_codes_fail_or_mark_suspect(sim: OpcuaSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    sim.set_status("Tank.Pressure", "UncertainLastUsableValue")
    assert (await bench.read("pressure")).suspect
    sim.set_status("Tank.Pressure", "BadSensorFailure")
    with pytest.raises(DriverError, match="BadSensorFailure"):
        await driver.read("pressure")
    await bench.close()


async def test_changes_use_the_node_data_type(sim: OpcuaSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert_done(await bench.write("speed", "1500 rpm"))
    assert sim.get("Pump.Speed") == 1500.0
    assert_done(await bench.write("setpoint", "40 %"))
    assert sim.get("Pump.Setpoint") == 40
    assert_failed(await bench.write("setpoint", "40.5 %"), "needs a whole number")
    assert sim.get("Pump.Setpoint") == 40
    assert_done(await bench.write("mode", "manual"))
    assert sim.get("Pump.Mode") == "manual"
    assert (await bench.read("speed")).value == 1500.0
    await bench.close()


async def test_methods_and_a_refusal(sim: OpcuaSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert_failed(await bench.act("prime"), "BadInvalidState")
    assert_done(await bench.act("start", rate="600 rpm"))
    assert sim.calls[-1] == ("Start", [600.0])
    assert sim.get("Pump.Running") is True
    assert_done(await bench.act("prime"))
    assert await bench.stop() == "safe"
    assert sim.calls[-1] == ("Stop", [])
    assert sim.get("Pump.Speed") == 0.0
    await bench.close()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        (
            'unit: degF, map: {{ node: "' + NS + 'Pump.Temperature"',
            'unit: V, map: {{ node: "' + NS + 'Pump.Temperature"',
            "doesn't convert",
        ),
        ('node: "' + NS + 'Tank.TempF"', 'node: "' + NS + 'Tank.Odd"', "zorp"),
        ('node: "' + NS + 'Pump.Running"', 'node: "' + NS + 'Pump"', "not a variable"),
        ('node: "' + NS + 'Pump.Running"', 'node: "ns=2;s=Pump.Nope"', "returned an error"),
        ('node: "' + NS + 'Pump.Running"', 'node: "nsu=urn:missing;s=X"', "has no namespace"),
        ('map: {{ node: "' + NS + 'Pump.Setpoint"', 'map: {{ node: "' + NS + 'Tank.Level"', "read only for this user"),
        ('method: "' + NS + 'Pump.Stop"', 'method: "' + NS + 'Pump.Speed"', "not a method"),
        ('method: "' + NS + 'Pump.Prime"', 'method: "' + NS + 'Pump.Start"', "takes 1 inputs"),
    ],
)
async def test_connect_refuses_files_that_do_not_fit_the_server(
    sim: OpcuaSim, old: str, new: str, message: str
) -> None:
    driver, bench = make(sim, _alter(old, new))
    with pytest.raises(DriverError, match=message):
        await bench.connect()
    assert driver.client is None
    await bench.close()


async def test_unknown_unit_works_with_a_map_unit(sim: OpcuaSim) -> None:
    text = _alter('node: "' + NS + 'Tank.TempF"', 'node: "' + NS + 'Tank.Odd", unit: degC')
    _driver, bench = make(sim, text)
    await bench.connect()
    assert (await bench.read("tank_temperature")).value == 1.0
    await bench.close()


async def test_a_stalled_server_times_out(sim: OpcuaSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    sim.hang(1.5)
    with pytest.raises(TimeoutError, match="sent no reply"):
        await driver.read("pressure")
    assert not (await driver.health()).connected
    await asyncio.sleep(1.5)
    await bench.connect()
    assert (await bench.read("pressure")).value == pytest.approx(1.013)
    await bench.close()


async def _connected(driver: OpcuaDriver) -> bool:
    return (await driver.health()).connected


async def test_lost_socket_and_reconnect(sim: OpcuaSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    driver.client.disconnect_socket()
    await eventually(lambda: _disconnected(driver))
    with pytest.raises(DriverError):
        await driver.read("pressure")
    await bench.connect()
    assert (await bench.read("pressure")).value == pytest.approx(1.013)
    await bench.close()


async def _disconnected(driver: OpcuaDriver) -> bool:
    return not (await driver.health()).connected


async def test_unreachable_and_silent_endpoints() -> None:
    driver = OpcuaDriver(loads('device: X\nid: x\nconnect: { opcua: "opc.tcp://127.0.0.1:9/", timeout: 300 ms }\n'))
    with pytest.raises((DriverError, TimeoutError)):
        await driver.connect()

    async def silent(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await asyncio.sleep(5)
        writer.close()

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        quiet = OpcuaDriver(
            loads(f'device: X\nid: x\nconnect: {{ opcua: "opc.tcp://127.0.0.1:{port}/", timeout: 300 ms }}\n')
        )
        with pytest.raises(TimeoutError):
            await quiet.connect()
    finally:
        server.close()
    assert await driver.describe() is None
    assert await driver.identify() == {"endpoint": "opc.tcp://127.0.0.1:9/"}


async def test_password_comes_from_the_environment(sim: OpcuaSim, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPCUA_TEST_PASSWORD", raising=False)
    text = SKID.replace("timeout: 600 ms", "timeout: 600 ms, user: operator, token_env: OPCUA_TEST_PASSWORD")
    _driver, bench = make(sim, text)
    with pytest.raises(DriverError, match="Set the OPCUA_TEST_PASSWORD"):
        await bench.connect()
    await bench.close()


async def test_describe_browses_variables_and_methods(sim: OpcuaSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["read"]["pump_temperature"] == {"map": {"node": "ns=2;s=Pump.Temperature"}, "unit": "degC"}
    assert proposal["read"]["tank_level"]["range"] == [0.0, 100.0]
    assert proposal["write"]["pump_speed"] == {
        "map": {"node": "ns=2;s=Pump.Speed"},
        "unit": "rpm",
        "min": 0.0,
        "max": 3000.0,
        "suggested": True,
    }
    assert proposal["write"]["pump_mode"]["type"] == "string"
    start = proposal["actions"]["pump_start"]
    assert start["map"]["inputs"] == ["rate"]
    assert start["args"]["rate"] == {"unit": "dimensionless", "min": 0, "max": 0}
    assert all(entry["suggested"] for entry in [*proposal["write"].values(), *proposal["actions"].values()])
    assert "tank_odd" in proposal["read"]
    await bench.close()


async def test_discovery_finds_the_server(sim: OpcuaSim, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OpcuaDriver, "discovery_urls", [sim.endpoint, "opc.tcp://127.0.0.1:9/"])
    found = await OpcuaDriver.discover()
    assert any(item.address == sim.endpoint for item in found)
    assert found[0].label == "OpenHAL OPC UA simulator"


def test_unece_codes_and_display_names() -> None:
    from asyncua import ua

    assert units.common_code(4408652) == "CEL"
    assert units.code_id("CEL") == 4408652
    assert units.common_code(units.code_id("P1")) == "P1"
    assert units.common_code(-1) == ""
    assert units.common_code(0x00FF00) == ""
    information = ua.EUInformation(UnitId=units.code_id("KPA"), DisplayName=ua.LocalizedText("kPa"))
    assert units.from_eu(information) == "kPa"
    assert units.from_eu(ua.EUInformation(UnitId=-1, DisplayName=ua.LocalizedText("°C"))) == "degC"
    assert units.from_eu(ua.EUInformation(UnitId=-1, DisplayName=ua.LocalizedText("zorp"))) is None


def test_node_ids_and_namespace_uris() -> None:
    assert channels.resolve("nsu=urn:a;s=X", ["http://opcfoundation.org/UA/", "urn:a"]) == "ns=1;s=X"
    assert channels.resolve("ns=3;i=7", []) == "ns=3;i=7"
    with pytest.raises(DriverError, match="has no namespace"):
        channels.resolve("nsu=urn:b;s=X", ["urn:a"])


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { a: { unit: V } }", "needs a map"),
        ("read: { a: { unit: V, map: { node: 'Pump.Speed' } } }", "not an OPC UA node id"),
        ("read: { a: { type: image, map: { node: 'i=1' } } }", "doesn't read images"),
        (
            "actions: { go: { args: { a: { unit: V, min: 0, max: 1 } }, map: { object: 'i=1', method: 'i=2' } } }",
            "map.inputs",
        ),
        ("actions: { go: { map: { object: 'i=1', method: 'nope' } } }", "not an OPC UA node id"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f'device: Bad\nid: bad\nconnect: {{ opcua: "opc.tcp://localhost:4840" }}\n{snippet}\n'
    with pytest.raises(DriverError, match=message):
        OpcuaDriver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"),
    [("timeout: 0 s", "timeout"), ("token_env: OPCUA_PW", "give user"), ("browse_depth: 9", "browse_depth")],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        OpcuaDriver(loads(f'device: Bad\nid: bad\nconnect: {{ opcua: "opc.tcp://localhost:4840", {params} }}\n'))


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/opcua/examples/dosing-pump.hal.yaml")
    assert not file.writable
    driver = OpcuaDriver(file)
    assert "start" in driver.actions
