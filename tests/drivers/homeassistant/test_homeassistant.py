"""The Home Assistant bridge over REST (mock transport) and WebSocket (a real local server)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.homeassistant.driver import HomeAssistantDriver, ha_unit
from openhal.drivers.homeassistant.simulator import HomeAssistantSim
from openhal.spec import loads
from openhal.spec.loader import from_data
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

HOME = """
device: Living room
id: living-room
connect:
  homeassistant: 127.0.0.1
  port: {port}
  token_env: HA_TEST_TOKEN
  timeout: 300 ms
  transport: {transport}
  entities:
    - light.desk_lamp
    - switch.heater_plug
    - fan.ceiling
    - number.pump_speed
    - select.mode
    - sensor.room_temperature
    - sensor.firmware
    - binary_sensor.window
read:
  room_temp: {{ unit: degC, map: {{ entity: sensor.room_temperature }} }}
  firmware: {{ type: string, map: {{ entity: sensor.firmware }} }}
  window_open: {{ type: bool, map: {{ entity: binary_sensor.window }} }}
  lamp_name: {{ type: string, map: {{ entity: light.desk_lamp, attribute: friendly_name }} }}
write:
  lamp_power: {{ type: bool, map: {{ entity: light.desk_lamp }} }}
  lamp_brightness: {{ unit: percent, min: 0, max: 100, map: {{ entity: light.desk_lamp }} }}
  lamp_color_temp: {{ unit: K, min: 2000, max: 7000, map: {{ entity: light.desk_lamp }} }}
  heater: {{ type: bool, map: {{ entity: switch.heater_plug }} }}
  fan_power: {{ type: bool, map: {{ entity: fan.ceiling }} }}
  fan_speed: {{ unit: percent, min: 0, max: 100, map: {{ entity: fan.ceiling }} }}
  fan_preset: {{ type: enum, values: [breeze, sleep, turbo], map: {{ entity: fan.ceiling }} }}
  pump: {{ unit: dimensionless, min: 0, max: 2, map: {{ entity: number.pump_speed }} }}
  mode: {{ type: enum, values: [eco, comfort, away, party], map: {{ entity: select.mode }} }}
safe_state: {{ heater: false, lamp_power: false }}
hazard: low
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture(autouse=True)
def token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HA_TEST_TOKEN", "ha-token")


def rest_bench(sim: HomeAssistantSim, text: str | None = None) -> Bench:
    file = loads(text or HOME.format(port=8123, transport="rest"))
    return Bench(file, HomeAssistantDriver(file, http_transport=sim.http_transport()))


@pytest.fixture
async def ws_sim() -> AsyncIterator[HomeAssistantSim]:
    sim = HomeAssistantSim()
    await sim.start_websocket()
    yield sim
    await sim.close()


def ws_bench(sim: HomeAssistantSim) -> Bench:
    file = loads(HOME.format(port=sim.port, transport="websocket"))
    return Bench(file, HomeAssistantDriver(file))


async def test_rest_reads_every_role() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    room = await bench.read("room_temp")
    assert room.unit == "degC"
    assert room.value == pytest.approx(22.0)
    assert (await bench.read("firmware")).value == "1.4.2"
    assert (await bench.read("window_open")).value is False
    assert (await bench.read("lamp_name")).value == "Desk lamp"
    assert (await bench.read("lamp_power")).value is False
    assert (await bench.read("lamp_brightness")).value == 0.0
    assert (await bench.read("lamp_color_temp")).value is None
    assert (await bench.read("fan_speed")).value == 0.0
    assert (await bench.read("fan_preset")).value is None
    assert (await bench.read("pump")).value == pytest.approx(0.2)
    assert (await bench.read("mode")).value == "eco"
    identity = await bench.driver.identify()
    assert identity["version"] == "2026.10.2"
    assert "light.desk_lamp" in identity["entities"]
    await bench.close()


async def test_rest_writes_call_the_right_services() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    lamp = sim.entities["light.desk_lamp"]
    assert_done(await bench.write("lamp_brightness", "40 %"))
    assert sim.calls[-1] == ("light", "turn_on", {"entity_id": "light.desk_lamp", "brightness_pct": 40.0})
    assert lamp["attributes"]["brightness"] == 102
    assert (await bench.read("lamp_brightness")).value == pytest.approx(40.0)
    assert_done(await bench.write("lamp_color_temp", "3000 K"))
    assert lamp["attributes"]["color_temp_kelvin"] == 3000
    assert_done(await bench.write("lamp_power", False))
    assert lamp["state"] == "off"
    assert_done(await bench.write("heater", True))
    assert sim.entities["switch.heater_plug"]["state"] == "on"
    assert_done(await bench.write("fan_speed", "50 %"))
    assert sim.calls[-1][:2] == ("fan", "set_percentage")
    assert (await bench.read("fan_power")).value is True
    assert_done(await bench.write("fan_preset", "sleep"))
    assert (await bench.read("fan_preset")).value == "sleep"
    assert_done(await bench.write("pump", "0.5 dimensionless"))
    assert sim.calls[-1] == ("number", "set_value", {"entity_id": "number.pump_speed", "value": 50.0})
    assert_done(await bench.write("mode", "away"))
    assert sim.entities["select.mode"]["state"] == "away"
    await bench.close()


async def test_home_assistant_errors_fail_writes() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    assert_failed(await bench.write("fan_preset", "turbo"), "not a valid preset_mode")
    assert_failed(await bench.write("pump", "1.5 dimensionless"), "outside valid range")
    assert_failed(await bench.write("mode", "party"), "not valid")
    await bench.close()


async def test_safe_state_comes_from_the_file() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    assert_done(await bench.write("heater", True))
    assert_done(await bench.write("lamp_power", True))
    assert await bench.stop() == "safe"
    assert sim.entities["switch.heater_plug"]["state"] == "off"
    assert sim.entities["light.desk_lamp"]["state"] == "off"
    await bench.close()


async def test_unavailable_and_unknown_entities() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    sim.entities["sensor.room_temperature"]["state"] = "unknown"
    assert (await bench.read("room_temp")).value is None
    sim.set_unavailable("switch.heater_plug")
    with pytest.raises(DriverError, match="unavailable in Home Assistant"):
        await bench.driver.read("heater")
    health = await bench.driver.health()
    assert not health.connected
    assert "switch.heater_plug" in health.detail
    await bench.close()


async def test_bad_states_are_malformed() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    sim.entities["sensor.room_temperature"]["state"] = "warm"
    with pytest.raises(DriverError, match="not a number"):
        await bench.driver.read("room_temp")
    sim.entities["sensor.room_temperature"]["state"] = "20"
    sim.entities["sensor.room_temperature"]["attributes"]["unit_of_measurement"] = "W"
    with pytest.raises(DriverError, match="doesn't convert"):
        await bench.driver.read("room_temp")
    sim.entities["switch.heater_plug"]["state"] = "maybe"
    with pytest.raises(DriverError, match="expected on or off"):
        await bench.driver.read("heater")
    sim.entities["select.mode"]["state"] = "vacation"
    with pytest.raises(DriverError, match="not one of"):
        await bench.driver.read("mode")
    del sim.entities["sensor.firmware"]
    with pytest.raises(DriverError, match=r"has no sensor\.firmware"):
        await bench.driver.read("firmware")
    await bench.close()


async def test_rest_transport_faults(monkeypatch: pytest.MonkeyPatch) -> None:
    sim = HomeAssistantSim()
    bench = rest_bench(sim)
    monkeypatch.delenv("HA_TEST_TOKEN")
    with pytest.raises(DriverError, match="Set the HA_TEST_TOKEN"):
        await bench.driver.connect()
    monkeypatch.setenv("HA_TEST_TOKEN", "nope")
    with pytest.raises(DriverError, match="refused the token"):
        await bench.driver.connect()
    monkeypatch.setenv("HA_TEST_TOKEN", "ha-token")
    await bench.connect()
    sim.latency_s = 1.0
    with pytest.raises(TimeoutError, match="didn't answer"):
        await bench.driver.read("room_temp")
    sim.latency_s = 0.0
    sim.malformed = True
    with pytest.raises(DriverError, match="not JSON"):
        await bench.driver.read("room_temp")
    sim.malformed = False
    sim.fail_http = True
    with pytest.raises(DriverError, match="Could not reach"):
        await bench.driver.read("room_temp")
    assert not (await bench.driver.health()).connected
    await bench.close()


async def test_describe_lists_the_selected_entities() -> None:
    sim = HomeAssistantSim()
    bench = await rest_bench(sim).connect()
    proposal = await bench.driver.describe()
    assert proposal is not None
    write, read = proposal["write"], proposal["read"]
    assert write["desk_lamp_brightness"]["map"] == {"entity": "light.desk_lamp", "attribute": "brightness"}
    assert write["desk_lamp_color_temp"]["min"] == 2200
    assert write["ceiling_speed"]["step"] == 25.0
    assert write["pump_speed_value"] == {
        "unit": "percent",
        "min": 0,
        "max": 100,
        "suggested": True,
        "map": {"entity": "number.pump_speed"},
        "step": 5,
    }
    assert write["mode_option"]["values"] == ["eco", "comfort", "away"]
    assert read["room_temperature_value"]["unit"] == "degF"
    assert read["firmware_value"]["type"] == "string"
    assert read["window_state"]["type"] == "bool"
    assert "front_door" not in str(proposal)
    assert all(entry["suggested"] for entry in write.values())
    data = {
        **proposal,
        "connect": {"homeassistant": "127.0.0.1", "entities": bench.driver.allowed},  # type: ignore[attr-defined]
    }
    file = from_data(data)
    assert not file.writable
    HomeAssistantDriver(file)
    await bench.close()


async def test_single_entity_file_uses_plain_names() -> None:
    sim = HomeAssistantSim()
    text = """
device: Desk lamp
connect: { homeassistant: 127.0.0.1, token_env: HA_TEST_TOKEN, entity: light.desk_lamp }
match: { homeassistant: "light.desk_*" }
write:
  power: { type: bool }
  brightness: { unit: percent, min: 1, max: 100, step: 1 }
safe_state: { power: false }
hazard: low
confirmed: { by: tester, at: 2026-10-24 }
"""
    bench = await rest_bench(sim, text).connect()
    assert_done(await bench.write("brightness", "75 %"))
    assert (await bench.read("power")).value is True
    proposal = await bench.driver.describe()
    assert proposal is not None
    assert set(proposal["write"]) == {"power", "brightness", "color_temp"}
    await bench.close()


async def test_websocket_reads_from_the_subscription(ws_sim: HomeAssistantSim) -> None:
    bench = await ws_bench(ws_sim).connect()
    driver = bench.driver
    assert isinstance(driver, HomeAssistantDriver)
    assert set(driver.cache) == set(driver.allowed)
    assert "lock.front_door" not in driver.cache
    assert (await bench.read("room_temp")).value == pytest.approx(22.0)
    assert_done(await bench.write("lamp_brightness", "60 %"))
    await eventually(lambda: _brightness_is(bench, 60.0))
    assert_failed(await bench.write("fan_preset", "turbo"), "not a valid preset_mode")
    assert (await driver.health()).connected
    await bench.close()


async def _brightness_is(bench: Bench, value: float) -> bool:
    reading = await bench.read("lamp_brightness")
    return reading.value == pytest.approx(value, abs=0.3)


async def test_websocket_disconnect_and_reconnect(ws_sim: HomeAssistantSim) -> None:
    bench = await ws_bench(ws_sim).connect()
    await ws_sim.drop_websockets()
    await eventually(lambda: _down(bench))
    with pytest.raises(DriverError, match="disconnected"):
        await bench.driver.read("room_temp")
    await bench.kernel.connection_lost(bench.device, "test")
    await bench.connect()
    assert (await bench.read("mode")).value == "eco"
    await bench.close()


async def _down(bench: Bench) -> bool:
    return not (await bench.driver.health()).connected


async def test_websocket_auth_timeout_and_malformed(ws_sim: HomeAssistantSim, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HA_TEST_TOKEN", "wrong")
    with pytest.raises(DriverError, match="refused the token"):
        await ws_bench(ws_sim).driver.connect()
    monkeypatch.setenv("HA_TEST_TOKEN", "ha-token")
    bench = await ws_bench(ws_sim).connect()
    ws_sim.latency_s = 1.0
    assert_failed(await bench.write("heater", True), "didn't answer call_service")
    ws_sim.latency_s = 0.0
    ws_sim.malformed = True
    assert_failed(await bench.write("heater", True), "malformed result")
    ws_sim.malformed = False
    await bench.close()


async def test_websocket_refused() -> None:
    file = loads(HOME.format(port=1, transport="websocket"))
    with pytest.raises(DriverError, match="Could not open the Home Assistant WebSocket"):
        await HomeAssistantDriver(file).connect()


def test_units_from_home_assistant() -> None:
    assert ha_unit("°C") == "degC"
    assert ha_unit("kWh") == "kWh"
    assert ha_unit("m/s") == "m/s"
    assert ha_unit("dBm") is None
    assert ha_unit("bananas") is None
    assert ha_unit(None) is None


@pytest.mark.parametrize(
    ("connect", "snippet", "message"),
    [
        ("entities: [light.a, light.b]", "write: { power: { type: bool } }", "needs map.entity"),
        ("entity: light.a", "write: { p: { type: bool, map: { entity: switch.b } } }", "doesn't select"),
        ("entity: sensor.t", "write: { value: { unit: degC, min: 0, max: 1 } }", "read-only"),
        ("entity: light.a", "write: { power: { unit: percent, min: 0, max: 1 } }", "type bool"),
        ("entity: light.a", "write: { brightness: { unit: V, min: 0, max: 1 } }", "converts to percent"),
        ("entity: lock.door", "write: { power: { type: bool } }", "doesn't know how"),
        ("entity: light.a", "read: { r: { type: string, map: { entity: light.a, extra: 1 } } }", "Extra inputs"),
        ("entity: light.a", "read: { r: { type: string, map: { entity: 'not an id' } } }", "should match pattern"),
        ("entity: light.a, entities: [light.b]", "", "not both"),
        ("entities: [Light.Bad]", "", "not an entity id"),
    ],
)
def test_bad_files_are_rejected(connect: str, snippet: str, message: str) -> None:
    text = f"device: Bad\nconnect: {{ homeassistant: h.local, {connect} }}\n{snippet}\n"
    with pytest.raises(Exception, match=message):
        HomeAssistantDriver(loads(text))


def test_match_pattern_must_cover_the_entities() -> None:
    text = """
device: Bad
match: { homeassistant: "light.desk_*" }
connect: { homeassistant: h.local, entity: switch.kettle }
read: { power: { type: bool } }
"""
    with pytest.raises(DriverError, match=r"doesn't match match\.homeassistant"):
        HomeAssistantDriver(loads(text))


def test_entities_named_only_in_maps_are_the_selection() -> None:
    text = """
device: Maps only
connect: { homeassistant: h.local }
read:
  a: { type: bool, map: { entity: binary_sensor.window } }
  b: { unit: degC, map: { entity: sensor.room_temperature } }
"""
    driver = HomeAssistantDriver(loads(text))
    assert driver.allowed == ["binary_sensor.window", "sensor.room_temperature"]
