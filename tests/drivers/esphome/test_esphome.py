"""The ESPHome driver, through the real aioesphomeapi client to the native API simulator."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.esphome import driver as esphome_driver
from openhal.drivers.esphome.driver import EspHomeDriver
from openhal.drivers.esphome.simulator import EspHomeSim
from openhal.spec import loads
from openhal.spec.loader import from_data
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

NODE = """
device: Greenhouse node
id: greenhouse
match: {{ esphome: {{ name: "plant-*", model: "esp32*" }} }}
connect: {{ esphome: 127.0.0.1, port: {port}, timeout: 400 ms{extra} }}
read:
  soil_moisture: {{ unit: percent }}
  air: {{ unit: degC, map: {{ object_id: air_temperature }} }}
  firmware: {{ type: string }}
  tank_empty: {{ type: bool }}
write:
  pump: {{ type: bool }}
  grow_light: {{ type: bool }}
  grow_light_brightness: {{ unit: percent, min: 0, max: 100 }}
  vent_fan: {{ type: bool }}
  vent_fan_speed: {{ unit: percent, min: 0, max: 100 }}
  vent_fan_preset: {{ type: enum, values: [auto, night] }}
  pump_minutes: {{ unit: min, min: 0, max: 1, map: {{ object_id: pump_seconds }} }}
  mode: {{ type: enum, values: [manual, schedule, off] }}
actions:
  calibrate: {{}}
safe_state: {{ pump: false, vent_fan: false }}
hazard: low
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture
async def sim() -> AsyncIterator[EspHomeSim]:
    node = EspHomeSim()
    await node.start()
    yield node
    await node.close()


def make(sim: EspHomeSim, *, text: str = NODE, extra: str = "") -> Bench:
    file = loads(text.format(port=sim.port, extra=extra))
    return Bench(file, EspHomeDriver(file))


async def test_connect_identifies_the_node(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    identity = await bench.driver.identify()
    assert identity["name"] == "plant-node"
    assert identity["model"] == "esp32dev"
    assert identity["esphome_version"] == "2026.10.1"
    assert identity["mac_address"] == "AA:BB:CC:DD:EE:FF"
    assert (await bench.driver.health()).detail == "plant-node"
    await bench.close()


async def test_reads_every_entity_kind(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    assert (await bench.read("soil_moisture")).value == pytest.approx(41.5)
    air = await bench.read("air")
    assert air.unit == "degC"
    assert air.value == pytest.approx(20.0)
    assert (await bench.read("firmware")).value == "2026.10.1"
    assert (await bench.read("tank_empty")).value is False
    assert (await bench.read("pump")).value is False
    assert (await bench.read("grow_light_brightness")).value == 0.0
    assert (await bench.read("vent_fan_speed")).value == 0.0
    assert (await bench.read("vent_fan_preset")).value is None
    assert (await bench.read("pump_minutes")).value == pytest.approx(10 / 60)
    assert (await bench.read("mode")).value == "manual"
    await sim.set_state("soil_moisture", state=12.0)
    await eventually(lambda: _value_is(bench, "soil_moisture", 12.0))
    await sim.set_state("soil_moisture", missing_state=True)
    await eventually(lambda: _value_is(bench, "soil_moisture", None))
    await bench.close()


async def _value_is(bench: Bench, channel: str, value: object) -> bool:
    return (await bench.read(channel)).value == value


async def test_writes_are_verified_against_state_updates(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    assert_done(await bench.write("pump", True))
    assert sim.entity("pump").state["state"] is True
    assert_done(await bench.write("grow_light_brightness", "40 %"))
    light = sim.entity("grow_light").state
    assert light["state"] is True
    assert light["brightness"] == pytest.approx(0.4)
    assert (await bench.read("grow_light")).value is True
    assert_done(await bench.write("grow_light_brightness", "0 %"))
    assert light["state"] is False
    assert_done(await bench.write("vent_fan_speed", "50 %"))
    assert sim.entity("vent_fan").state["speed_level"] == 2
    assert (await bench.read("vent_fan_speed")).value == pytest.approx(66.667)
    assert_done(await bench.write("vent_fan_preset", "night"))
    assert (await bench.read("vent_fan_preset")).value == "night"
    assert_done(await bench.write("vent_fan", False))
    assert_done(await bench.write("pump_minutes", "0.25 min"))
    assert sim.entity("pump_seconds").state["state"] == pytest.approx(15.0)
    assert_done(await bench.write("mode", "schedule"))
    assert sim.entity("mode").state["state"] == "schedule"
    await bench.close()


async def test_a_command_the_device_ignores_fails(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    sim.ignore_commands = True
    assert_failed(await bench.write("pump", True), "didn't report pump = True")
    assert (await bench.read("pump")).value is False
    sim.ignore_commands = False
    await bench.close()


async def test_button_action(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    assert_done(await bench.act("calibrate"))
    await eventually(lambda: _pressed(sim))
    await bench.close()


async def _pressed(sim: EspHomeSim) -> bool:
    return sim.button_presses == 1


async def test_safe_state_comes_from_the_file(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    assert_done(await bench.write("pump", True))
    assert_done(await bench.write("vent_fan", True))
    assert await bench.stop() == "safe"
    assert sim.entity("pump").state["state"] is False
    assert sim.entity("vent_fan").state["state"] is False
    await bench.close()


async def test_disconnect_and_reconnect(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    await sim.drop_connections()
    await eventually(lambda: _down(bench))
    with pytest.raises(DriverError, match="disconnected"):
        await bench.driver.read("pump")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert (await bench.read("mode")).value == "manual"
    await bench.close()


async def _down(bench: Bench) -> bool:
    return not (await bench.driver.health()).connected


async def test_garbage_from_the_device_ends_the_session(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    sim.garbage_next = True
    await sim.set_state("soil_moisture", state=1.0)
    await eventually(lambda: _down(bench))
    await bench.close()


async def test_slow_device_times_out(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    driver = bench.driver
    assert isinstance(driver, EspHomeDriver)
    sim.latency_s = 1.0
    driver.states.clear()
    with pytest.raises(TimeoutError, match="didn't report a state"):
        await driver.read("pump")
    sim.latency_s = 0.0
    await bench.close()
    sim.latency_s = 1.0
    with pytest.raises(TimeoutError, match="didn't finish the ESPHome handshake"):
        await driver.connect()


async def test_connection_problems(sim: EspHomeSim, monkeypatch: pytest.MonkeyPatch) -> None:
    file = loads(NODE.format(port=1, extra=""))
    with pytest.raises(DriverError, match=r"ESPHome at 127\.0\.0\.1"):
        await EspHomeDriver(file).connect()
    bench = make(sim, extra=", noise_psk_env: NODE_PSK")
    monkeypatch.delenv("NODE_PSK", raising=False)
    with pytest.raises(DriverError, match="Set the NODE_PSK"):
        await bench.driver.connect()
    monkeypatch.setenv("NODE_PSK", "QRTIErOb/fcE9Ez4PO8kZpfR/Q8k8U5fhvM2ttUzJw8=")
    with pytest.raises((DriverError, TimeoutError)):
        await bench.driver.connect()


async def test_match_and_binding_errors(sim: EspHomeSim) -> None:
    bench = make(sim, text=NODE.replace('name: "plant-*"', 'name: "kitchen-*"'))
    with pytest.raises(DriverError, match=r"doesn't match match\.esphome"):
        await bench.driver.connect()
    cases = [
        ("  firmware: {{ type: string }}", "  ghost: {{ type: string }}", "no entity 'ghost'. It has"),
        ("  mode: {{ type: enum, values: [manual, schedule, off] }}", "  mode: {{ type: bool }}", "type enum"),
        (
            "  pump: {{ type: bool }}",
            "  pump: {{ type: bool }}\n  soil: {{ type: bool, map: {{ object_id: tank_empty }} }}",
            "read-only",
        ),
        (
            "  mode: {{ type: enum",
            "  pump_seconds_brightness: {{ unit: percent, min: 0, max: 1 }}\n  mode: {{ type: enum",
            "no brightness",
        ),
        ("  calibrate: {{}}", "  calibrate: {{ map: {{ object_id: pump }} }}", "not a button"),
        ("  vent_fan_speed: {{ unit: percent,", "  vent_fan_speed: {{ unit: dimensionless,", "in percent"),
    ]
    for old, new, message in cases:
        text = NODE.replace(old, new)
        assert text != NODE
        bench = make(sim, text=text)
        with pytest.raises(DriverError, match=message):
            await bench.driver.connect()


def test_static_validation() -> None:
    with pytest.raises(DriverError, match="take no arguments"):
        EspHomeDriver(
            loads("device: x\nconnect: { esphome: h }\nactions: { a: { args: { n: { unit: s, min: 0, max: 1 } } } }")
        )
    with pytest.raises(DriverError, match="Extra inputs"):
        EspHomeDriver(loads("device: x\nconnect: { esphome: h }\nread: { a: { type: bool, map: { key: 5 } } }"))
    with pytest.raises(Exception, match="needs a unit"):
        EspHomeDriver(loads("device: x\nconnect: { esphome: h, timeout: 3 }"))
    driver = EspHomeDriver(loads("device: x\nconnect: { esphome: h }\nread: { fan_preset: { type: string } }"))
    assert driver.bindings["fan_preset"].object_id == "fan"


async def test_not_connected() -> None:
    driver = EspHomeDriver(loads("device: x\nconnect: { esphome: h }\nwrite: { pump: { type: bool } }"))
    assert await driver.identify() == {"host": "h"}
    assert await driver.describe() is None
    assert not (await driver.health()).connected


async def test_describe_proposes_every_entity(sim: EspHomeSim) -> None:
    bench = await make(sim).connect()
    proposal = await bench.driver.describe()
    assert proposal is not None
    assert proposal["device"] == {"name": "Plant node", "model": "esp32dev", "manufacturer": "Espressif"}
    assert proposal["match"]["esphome"] == {"name": "plant-node"}
    assert proposal["read"]["air_temperature"] == {"unit": "degF"}
    assert proposal["write"]["vent_fan_speed"]["step"] == pytest.approx(33.3333)
    assert proposal["write"]["pump_seconds"]["max"] == 30.0
    assert proposal["write"]["grow_light_brightness"]["unit"] == "percent"
    assert "calibrate" in proposal["actions"]
    file = from_data({**proposal, "connect": {"esphome": "127.0.0.1", "port": sim.port}})
    assert not file.writable
    fresh = EspHomeDriver(file)
    await fresh.connect()
    await fresh.close()
    await bench.close()


async def test_discover_uses_mdns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(seconds: float) -> list[tuple[str, str, int, dict[str, str]]]:
        return [("plant-node", "192.168.1.40", 6053, {"friendly_name": "Plant node", "version": "2026.10.1"})]

    monkeypatch.setattr(esphome_driver, "_browse", fake)
    found = await EspHomeDriver.discover()
    assert found[0].address == "192.168.1.40:6053"
    assert found[0].identifiers["esphome.name"] == "plant-node"
    assert found[0].label == "Plant node"

    async def broken(seconds: float) -> list[tuple[str, str, int, dict[str, str]]]:
        raise OSError("no multicast")

    monkeypatch.setattr(esphome_driver, "_browse", broken)
    assert await EspHomeDriver.discover() == []
