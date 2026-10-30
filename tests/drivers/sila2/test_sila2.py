"""The SiLA 2 driver, against a thermoshaker served by the sila2 package's own server."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.sila2 import channels
from openhal.drivers.sila2.driver import Sila2Driver
from openhal.drivers.sila2.simulator import ThermoShakerSim
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

SHAKER = """
device: Test thermoshaker
id: shaker
connect: {{ sila2: 127.0.0.1, port: {port}, insecure: true, timeout: 1 s, action_wait: 2 s }}
read:
  temperature: {{ unit: degF, stream: true, map: {{ feature: TemperatureController, property: CurrentTemperature }} }}
  lid_closed: {{ type: bool, map: {{ feature: TemperatureController, property: DeviceState, field: LidClosed }} }}
  mode:
    type: enum
    values: [idle, shaking]
    map: {{ feature: TemperatureController, property: DeviceState, field: Mode }}
  speed: {{ unit: rpm, stream: true, map: {{ feature: ShakeController, property: ShakingSpeed }} }}
write:
  target:
    unit: degC
    min: 4
    max: 95
    map:
      feature: TemperatureController
      command: SetTargetTemperature
      parameter: TargetTemperature
      readback: TargetTemperature
actions:
  shake:
    args: {{ rpm: {{ unit: rpm, min: 0, max: 1500 }}, seconds: {{ unit: s, min: 0, max: 600 }} }}
    map: {{ feature: ShakeController, command: Shake, parameters: {{ rpm: Speed, seconds: Duration }} }}
  stop_shaking: {{ map: {{ feature: ShakeController, command: StopShaking }} }}
safe_state:
  - {{ action: stop_shaking }}
hazard: medium
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture
def sim() -> Iterator[ThermoShakerSim]:
    server = ThermoShakerSim()
    server.start()
    yield server
    server.stop()


def make(sim: ThermoShakerSim, text: str = SHAKER) -> tuple[Sila2Driver, Bench]:
    file = loads(text.format(port=sim.port))
    driver = Sila2Driver(file)
    return driver, Bench(file, driver)


async def _value(bench: Bench, channel: str, wanted: object) -> bool:
    return (await bench.read(channel)).value == wanted


async def test_connect_binds_features_and_identifies_the_server(sim: ThermoShakerSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    identity = await driver.identify()
    assert identity["ServerName"] == "Simulated thermoshaker"
    assert identity["ServerType"] == "ThermoShaker"
    assert identity["ServerUUID"] == "7c0e9a1e-56c4-4c37-9f43-6f5b1f0e2a11"
    assert driver.bindings["temperature"].observable
    assert driver.bindings["temperature"].unit == "degC"
    assert driver.bindings["speed"].kind == "Integer"
    assert (await driver.health()).connected
    await bench.close()


async def test_streams_structures_and_unit_conversion(sim: ThermoShakerSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    await eventually(lambda: _value(bench, "temperature", pytest.approx(71.6)))
    sim.push_temperature(30.0)
    await eventually(lambda: _value(bench, "temperature", pytest.approx(86.0)))
    assert (await bench.read("lid_closed")).value is True
    assert (await bench.read("mode")).value == "idle"
    assert (await bench.read("speed")).value == 0.0
    await bench.close()


async def test_a_stream_read_before_its_first_value_asks_the_server(sim: ThermoShakerSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    driver.latest.clear()
    assert (await driver.read("speed")).value == 0.0
    await bench.close()


async def test_target_temperature_changes_through_a_command(sim: ThermoShakerSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert_done(await bench.write("target", "40 degC"))
    assert sim.calls[-1] == ("SetTargetTemperature", (40.0,))
    assert (await bench.read("target")).value == 40.0
    await eventually(lambda: _value(bench, "temperature", pytest.approx(104.0)))
    await bench.close()


async def test_defined_execution_error_fails_the_change(sim: ThermoShakerSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    decision = await bench.write("target", "90 degC")
    assert_failed(decision, "TooHot")
    assert "lid limit" in decision.message
    assert sim.block.target == 22.0
    await bench.close()


async def test_validation_error_from_constraints(sim: ThermoShakerSim) -> None:
    text = SHAKER.replace("min: 4\n    max: 95", "min: 0\n    max: 95")
    _driver, bench = make(sim, text)
    await bench.connect()
    assert_failed(await bench.write("target", "1 degC"), "returned an error for the parameters")
    await bench.close()


async def test_observable_command_finishes(sim: ThermoShakerSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert_done(await bench.act("shake", rpm="600 rpm", seconds="200 ms"))
    assert sim.calls[-1] == ("Shake", (600, 0.2))
    await eventually(lambda: _value(bench, "speed", 0.0))
    await bench.close()


async def test_long_observable_command_returns_started_and_stop_ends_it(sim: ThermoShakerSim) -> None:
    text = SHAKER.replace("action_wait: 2 s", "action_wait: 200 ms")
    driver, bench = make(sim, text)
    await bench.connect()
    assert_done(await bench.act("shake", rpm="900 rpm", seconds="60 s"))
    assert len(driver.running) == 1
    await eventually(lambda: _value(bench, "speed", 900.0))
    assert await bench.stop() == "safe"
    assert sim.calls[-1] == ("StopShaking", ())
    await eventually(lambda: _value(bench, "speed", 0.0))
    await bench.close()


async def test_integer_parameters_take_whole_numbers(sim: ThermoShakerSim) -> None:
    _driver, bench = make(sim)
    await bench.connect()
    assert_failed(await bench.act("shake", rpm="600.5 rpm", seconds="1 s"), "not a whole number")
    assert_done(await bench.act("shake", rpm="600 rpm", seconds="100 ms"))
    assert sim.calls[-1] == ("Shake", (600, 0.1))
    await bench.close()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("feature: ShakeController, property", "feature: Centrifuge, property", "doesn't implement Centrifuge"),
        ("property: ShakingSpeed", "property: Wobble", "has no property Wobble"),
        ("command: StopShaking", "command: Fly", "has no command Fly"),
        ("parameter: TargetTemperature\n", "parameter: Target\n", "has no parameter Target"),
        (
            "parameters: {{ rpm: Speed, seconds: Duration }}",
            "parameters: {{ rpm: Speed, seconds: Time }}",
            "no parameters",
        ),
        ("speed: {{ unit: rpm,", "speed: {{ unit: V,", "doesn't convert"),
        ("field: LidClosed }}", "field: Hinge }}", None),
        ("property: DeviceState, field: Mode", "property: DeviceState", "needs a field"),
        ("readback: TargetTemperature", "readback: Nothing", "no property Nothing"),
        (
            "feature: TemperatureController, property: CurrentTemperature",
            "feature: org.openhal/examples/TemperatureController/v2, property: CurrentTemperature",
            "not org.openhal/examples/TemperatureController/v2",
        ),
    ],
)
async def test_connect_refuses_files_that_do_not_fit_the_server(
    sim: ThermoShakerSim, old: str, new: str, message: str | None
) -> None:
    assert old in SHAKER
    driver, bench = make(sim, SHAKER.replace(old, new))
    if message is None:
        await bench.connect()
        with pytest.raises(DriverError, match="has no field Hinge"):
            await driver.read("lid_closed")
    else:
        with pytest.raises(DriverError, match=message):
            await bench.connect()
        assert driver.client is None
    await bench.close()


async def test_slow_server_times_out(sim: ThermoShakerSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    sim.block.delay_s = 2.0
    with pytest.raises(TimeoutError, match="sent no reply to reading mode"):
        await driver.read("mode")
    sim.block.delay_s = 0.0
    await bench.close()


async def test_server_restart_and_reconnect(sim: ThermoShakerSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    sim.stop()
    await eventually(lambda: _disconnected(driver), within=5)
    with pytest.raises(DriverError):
        await driver.read("mode")
    sim.restart()
    await bench.connect()
    assert (await bench.read("mode")).value == "idle"
    await bench.close()


async def _disconnected(driver: Sila2Driver) -> bool:
    return not (await driver.health()).connected


async def test_unreachable_server() -> None:
    driver = Sila2Driver(
        loads("device: X\nid: x\nconnect: { sila2: 127.0.0.1, port: 9, insecure: true, timeout: 500 ms }\n")
    )
    with pytest.raises((DriverError, TimeoutError)):
        await driver.connect()
    assert not (await driver.health()).connected
    assert await driver.describe() is None
    assert await driver.identify() == {"server": "127.0.0.1:9"}


async def test_describe_proposes_reads_and_actions(sim: ThermoShakerSim) -> None:
    driver, bench = make(sim)
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    current = proposal["read"]["temperature_controller_current_temperature"]
    assert current == {
        "unit": "degC",
        "stream": True,
        "map": {"feature": "TemperatureController", "property": "CurrentTemperature"},
    }
    assert proposal["read"]["shake_controller_shaking_speed"]["range"] == [0.0, 3000.0]
    target = proposal["actions"]["temperature_controller_set_target_temperature"]
    assert target["args"]["target_temperature"] == {"unit": "degC", "min": 4.0, "max": 95.0}
    shake = proposal["actions"]["shake_controller_shake"]
    assert shake["map"]["parameters"] == {"speed": "Speed", "duration": "Duration"}
    assert shake["args"]["duration"] == {"unit": "s", "min": 0, "max": 0}
    assert all(entry["suggested"] for entry in proposal["actions"].values())
    assert "TemperatureController.DeviceState" in proposal["notes"]
    await bench.close()


async def test_discovery_lists_mdns_services(monkeypatch: pytest.MonkeyPatch) -> None:
    async def browse(wait: float) -> list[tuple[str, str, int, dict[str, str]]]:
        await asyncio.sleep(0)
        return [("Thermoshaker", "192.168.1.30", 50052, {"version": "1.0", "server_name": "Thermoshaker"})]

    monkeypatch.setattr(Sila2Driver, "_browse", classmethod(lambda cls, wait: browse(wait)))
    found = await Sila2Driver.discover()
    assert found[0].address == "sila://192.168.1.30:50052"
    assert found[0].identifiers["sila.version"] == "1.0"


def test_field_paths_into_structures() -> None:
    from collections import namedtuple

    state = namedtuple("State", ["Lid", "Mode"])(namedtuple("Lid", ["Closed"])(True), "idle")
    assert channels.get_field(state, "Lid.Closed") is True
    assert channels.get_field(state, None) is state
    with pytest.raises(KeyError):
        channels.get_field(state, "Lid.Open")


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { a: { unit: V } }", "needs a map"),
        ("read: { a: { unit: V, map: { feature: lowercase, property: X } } }", "String should match"),
        ("read: { a: { type: image, map: { feature: F, property: X } } }", "doesn't read images"),
        (
            "actions: { go: { args: { a: { unit: V, min: 0, max: 1 } }, map: { feature: F, command: Go } } }",
            "map.parameters",
        ),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ sila2: localhost }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        Sila2Driver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("timeout: 0 s", "timeout"),
        ("action_wait: 20 s", "action_wait"),
        ("insecure: true, ca_env: SILA_CA", "ca_env"),
        ("ca_file: ca.pem", "ca_file"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Sila2Driver(loads(f"device: Bad\nid: bad\nconnect: {{ sila2: localhost, {params} }}\n"))


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/sila2/examples/thermoshaker.hal.yaml")
    assert not file.writable
    driver = Sila2Driver(file)
    assert "shake" in driver.actions


BOOTSTRAP = """
import asyncio
import sys
from google.protobuf.internal import api_implementation
import google.protobuf.descriptor_pool
assert api_implementation.Type() != "python"
from openhal.drivers.sila2.driver import Sila2Driver
from openhal.drivers.sila2.simulator import ThermoShakerSim
from openhal.spec import loads

async def main():
    sim = ThermoShakerSim()
    port = sim.start()
    driver = Sila2Driver(loads(f"device: X\\nid: x\\nconnect: {{ sila2: 127.0.0.1, port: {port}, insecure: true }}\\n"))
    await driver.connect()
    print("server", (await driver.identify())["ServerName"])
    await driver.close()
    sim.stop()

asyncio.run(main())
"""


def test_sila2_loads_when_protobuf_was_imported_first() -> None:
    import os
    import subprocess

    environment = {key: value for key, value in os.environ.items() if key != "PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"}
    result = subprocess.run(
        [sys.executable, "-c", BOOTSTRAP],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).parents[3],
        env=environment,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "server Simulated thermoshaker" in result.stdout


def test_the_ca_certificate_path_comes_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from openhal.drivers.sila2.driver import _certificate

    monkeypatch.delenv("SILA_TEST_CA", raising=False)
    with pytest.raises(DriverError, match="Set the SILA_TEST_CA environment variable"):
        _certificate("SILA_TEST_CA")
    pem = tmp_path / "ca.pem"
    pem.write_bytes(b"-----BEGIN CERTIFICATE-----\n")
    monkeypatch.setenv("SILA_TEST_CA", str(pem))
    assert _certificate("SILA_TEST_CA") == b"-----BEGIN CERTIFICATE-----\n"
    monkeypatch.setenv("SILA_TEST_CA", str(tmp_path / "missing.pem"))
    with pytest.raises(DriverError, match="Could not read the CA certificate"):
        _certificate("SILA_TEST_CA")
