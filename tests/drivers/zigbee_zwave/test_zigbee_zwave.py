"""The zigbee-zwave driver, against a simulated Zigbee2MQTT on the MQTT broker and a simulated zwave-js-server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest

from openhal.conformance import run
from openhal.drivers.base import DriverError
from openhal.drivers.mqtt.conformance import wait_until
from openhal.drivers.mqtt.simulator import MqttBroker
from openhal.drivers.zigbee_zwave.conformance import wait_disconnected, zigbee_file, zwave_case, zwave_file
from openhal.drivers.zigbee_zwave.driver import ZigbeeZWaveDriver
from openhal.drivers.zigbee_zwave.simulator import Zigbee2MqttSim, ZWaveJsSim
from openhal.drivers.zigbee_zwave.zigbee import features
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "zigbee_zwave" / "examples"
WHO = human("tester")
SENSOR = """
read:
  temperature: { unit: degF }
  humidity: { unit: percent, range: [0, 100] }
  battery: { unit: percent }
"""
PLUG = """
read:
  power: { unit: W, map: { command_class: 50, property: value, property_key: 66049 } }
  energy: { unit: kWh, map: { command_class: 50, property: value, property_key: 65537 } }
write:
  relay: { type: bool, map: { command_class: 37, property: currentValue } }
safe_state: { relay: false }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""
MULTISENSOR = """
read:
  temperature: { unit: degC, map: { command_class: 49, property: Air temperature } }
  motion:
    type: enum
    values: [idle, Motion detection]
    map: { command_class: 113, property: Home Security, property_key: Motion sensor status }
"""


@pytest.fixture
def broker() -> Iterator[MqttBroker]:
    with MqttBroker() as running:
        yield running


@pytest.fixture
def zigbee(broker: MqttBroker) -> Zigbee2MqttSim:
    return Zigbee2MqttSim(broker).attach()


@pytest.fixture
async def zwave() -> AsyncIterator[ZWaveJsSim]:
    sim = await ZWaveJsSim().start()
    yield sim
    await sim.close()


async def connected(file: DeviceFile, **kwargs: Any) -> ZigbeeZWaveDriver:
    driver = ZigbeeZWaveDriver(file, **kwargs)
    await driver.connect()
    return driver


async def kernel_for(driver: ZigbeeZWaveDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = '{ zigbee-zwave: "mqtt://broker.local", friendly_name: lamp }') -> DeviceFile:
    return loads(f"device: T\nid: t\nconnect: {connect}\n{channels}\n")


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ('{ zigbee-zwave: "mqtt://b" }', "need friendly_name"),
        ('{ zigbee-zwave: "mqtt://b", friendly_name: x, node: 3 }', "need friendly_name and no node"),
        ('{ zigbee-zwave: "ws://b:3000" }', "need node"),
        ('{ zigbee-zwave: "ws://b:3000", node: 3, friendly_name: x }', "no friendly_name"),
        ('{ zigbee-zwave: "http://b", friendly_name: x }', "pattern"),
        ('{ zigbee-zwave: "mqtt://b", friendly_name: "a/#" }', "wildcards"),
        ('{ zigbee-zwave: "mqtt://b", friendly_name: x, colour: red }', "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ZigbeeZWaveDriver(bare("read:\n  state: { type: bool }", connect))


@pytest.mark.parametrize(
    ("channels", "connect", "message"),
    [
        ("actions:\n  go: {}", None, "no actions"),
        ("read:\n  cam: { type: image }", None, "no image"),
        ("read:\n  x: { type: bool, map: { command_class: 37 } }", None, "Z-Wave keys"),
        ("read:\n  x: { type: bool, map: { scale: 0 } }", None, "scale"),
        ("read:\n  x: { type: bool, map: { colour: red } }", None, "Extra inputs"),
        (
            "read:\n  x: { type: bool, map: { property: currentValue } }",
            '{ zigbee-zwave: "ws://z", node: 2 }',
            "need command_class",
        ),
    ],
)
def test_bad_maps(channels: str, connect: str | None, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        ZigbeeZWaveDriver(bare(channels, connect) if connect else bare(channels))


def test_exposes_flatten_lights_and_composites() -> None:
    found = features(
        [
            {
                "type": "light",
                "features": [
                    {"type": "binary", "property": "state", "access": 7, "value_on": "ON", "value_off": "OFF"}
                ],
            },
            {"type": "composite", "property": "color", "features": [{"type": "numeric", "property": "x", "access": 7}]},
            {"type": "text", "property": "note", "access": 2},
            {"type": "list", "property": "schedule", "access": 3},
            "junk",
        ]
    )
    assert set(found) == {"state", "color.x", "note"}
    assert (found["state"].on, found["state"].off, found["state"].writable) == ("ON", "OFF", True)
    assert found["note"].kind == "string"
    assert not found["note"].readable


async def test_zigbee_reads_come_from_the_device_topic(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker))
    await wait_until(lambda: driver.link._state.get("brightness") is not None)
    assert (await driver.read("state")).value is False
    brightness = await driver.read("brightness")
    assert brightness.value == pytest.approx(50.0)
    assert brightness.unit == "percent"
    assert (await driver.read("power_on_behavior")).value == "previous"
    assert (await driver.read("linkquality")).value == 120.0
    get = next(json.loads(payload) for topic, payload, *_ in broker.published if topic.endswith("desk_lamp/get"))
    assert set(get) == {"brightness", "state", "power_on_behavior"}
    identity = await driver.identify()
    assert (identity["vendor"], identity["model"]) == ("IKEA", "LED1545G12")
    await driver.close()


async def test_sensors_read_unknown_until_they_report(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker, name="hall_sensor", channels=SENSOR))
    assert (await driver.read("temperature")).value is None
    zigbee.report("hall_sensor", {"humidity": 120.0})
    await wait_until(lambda: "temperature" in driver.link._state)
    assert (await driver.read("temperature")).value == pytest.approx(70.52)
    humidity = await driver.read("humidity")
    assert humidity.value == 120.0
    assert humidity.suspect
    assert (await driver.read("battery")).value == 91.0
    await driver.close()


async def test_zigbee_commands_go_to_the_set_topic(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker))
    kernel = await kernel_for(driver)
    for channel, value in (("brightness", "75 percent"), ("state", False), ("power_on_behavior", "off")):
        decision = await kernel.execute(Write(device="conformance-zigbee", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert zigbee.commands == [
        ("desk_lamp", {"brightness": 191}),
        ("desk_lamp", {"state": "OFF"}),
        ("desk_lamp", {"power_on_behavior": "off"}),
    ]
    await wait_until(lambda: driver.link._state.get("power_on_behavior") == "off")
    assert (await driver.read("brightness")).value == pytest.approx(75.2, abs=0.1)
    assert (await driver.read("state")).value is False
    await driver.close()


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("write:\n  linkquality: { unit: dimensionless, min: 0, max: 255 }", "can't be set"),
        ("read:\n  state: { unit: dimensionless }", "needs type bool"),
        ("read:\n  brightness: { type: bool }", "needs type number"),
        ("read:\n  power_on_behavior: { type: bool }", "needs type enum"),
        ("read:\n  power_on_behavior: { type: enum, values: [sometimes] }", "doesn't list sometimes"),
        ("read:\n  wattage: { unit: W }", "doesn't have this value"),
    ],
)
async def test_channels_the_bridge_cannot_serve_are_refused(
    broker: MqttBroker, zigbee: Zigbee2MqttSim, channels: str, message: str
) -> None:
    driver = ZigbeeZWaveDriver(zigbee_file(broker, channels=channels))
    with pytest.raises(DriverError, match=message):
        await driver.connect()
    assert not (await driver.health()).connected


async def test_units_that_do_not_convert_are_refused(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = ZigbeeZWaveDriver(zigbee_file(broker, name="hall_sensor", channels="read:\n  temperature: { unit: V }"))
    with pytest.raises(DriverError, match="doesn't convert to V"):
        await driver.connect()


async def test_unknown_devices_and_topics_are_explained(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    with pytest.raises(DriverError, match="no device named 'porch'"):
        await connected(zigbee_file(broker, name="porch"))
    with pytest.raises(DriverError, match="nothing retained on z2m/bridge/devices"):
        await connected(zigbee_file(broker, extra=", base_topic: z2m", timeout="500 ms"))


async def test_availability_and_bridge_state_drive_health(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker))
    assert (await driver.health()).connected
    zigbee.offline("desk_lamp")
    await wait_until(lambda: driver.link._availability == "offline")
    health = await driver.health()
    assert not health.connected
    assert "offline in Zigbee2MQTT" in health.detail
    await driver.close()
    driver = await connected(zigbee_file(broker, name="hall_sensor", channels=SENSOR))
    zigbee.bridge_offline()
    await wait_until(lambda: driver.link._bridge == "offline")
    assert "reports itself offline" in (await driver.health()).detail
    await driver.close()


async def test_a_dropped_broker_is_reported_and_reconnects(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker))
    broker.kick_all()
    await wait_disconnected(driver)
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("state")
    await driver.connect()
    assert (await driver.health()).connected
    await driver.close()
    with pytest.raises(DriverError, match="Connect it first"):
        await driver.read("state")


async def test_a_missing_puback_drops_the_session(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker, timeout="300 ms"))
    kernel = await kernel_for(driver)
    broker.hold_acks = True
    decision = await kernel.execute(Write(device="conformance-zigbee", channel="state", value=True), WHO)
    assert decision.status == "failed"
    assert "can't arrive late" in decision.message
    assert not (await driver.health()).connected


async def test_broker_credentials() -> None:
    with MqttBroker(username="z2m", password="hunter2") as secured:
        Zigbee2MqttSim(secured).attach()
        extra = ", username: z2m, token_env: Z2M_PASSWORD"
        file = zigbee_file(secured, extra=extra)
        driver = await connected(file, environ={"Z2M_PASSWORD": "hunter2"}.get)
        assert (await driver.health()).connected
        await driver.close()
        with pytest.raises(DriverError, match="Check the user name"):
            await connected(file, environ={"Z2M_PASSWORD": "wrong"}.get)
        with pytest.raises(DriverError, match="Z2M_PASSWORD"):
            await connected(file, environ=lambda name: None)


async def test_unreachable_brokers_fail_with_the_address() -> None:
    driver = ZigbeeZWaveDriver(
        bare("read:\n  state: { type: bool }", '{ zigbee-zwave: "mqtt://127.0.0.1:1", friendly_name: x }')
    )
    with pytest.raises(DriverError, match=r"127\.0\.0\.1:1"):
        await driver.connect()


async def test_zigbee_describe_proposes_exposed_features(broker: MqttBroker, zigbee: Zigbee2MqttSim) -> None:
    driver = await connected(zigbee_file(broker))
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["brightness"] == {
        "unit": "dimensionless",
        "min": 0,
        "max": 254,
        "map": {"property": "brightness"},
        "suggested": True,
    }
    assert proposal["write"]["state"]["type"] == "bool"
    assert proposal["read"]["linkquality"]["unit"] == "dimensionless"
    assert proposal["device"]["manufacturer"] == "IKEA"
    await driver.close()
    assert await driver.describe() is None


async def test_zwave_reads_values_from_the_node(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave, node=2, channels=PLUG))
    assert zwave.chosen_schema == 40
    assert (await driver.read("relay")).value is False
    assert (await driver.read("power")).value == 0.0
    energy = await driver.read("energy")
    assert energy.value == 12.75
    assert energy.unit == "kWh"
    identity = await driver.identify()
    assert (identity["manufacturer"], identity["model"], identity["firmware"]) == ("Zooz", "ZEN04", "1.40")
    await driver.close()
    sensor = await connected(zwave_file(zwave, node=4, channels=MULTISENSOR))
    assert (await sensor.read("temperature")).value == 22.1
    assert (await sensor.read("motion")).value == "idle"
    await zwave.update(4, 113, "Home Security", 8, "Motion sensor status")
    await wait_until(lambda: sensor.link.values[(113, 0, "Home Security", "Motion sensor status")][0] == 8)
    assert (await sensor.read("motion")).value == "Motion detection"
    await sensor.close()


async def test_zwave_changes_go_to_the_target_value(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave, node=2, channels=PLUG))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(Write(device="conformance-zwave", channel="relay", value=True), WHO)
    assert decision.status == "done", decision.message
    call = zwave.calls[-1]
    assert call["command"] == "node.set_value"
    assert call["valueId"] == {"commandClass": 37, "endpoint": 0, "property": "targetValue"}
    assert call["value"] is True
    await wait_until(lambda: driver.link.values[(37, 0, "currentValue", "")][0] is True)
    assert (await driver.read("relay")).value is True
    await driver.close()


async def test_old_schemas_report_success_as_a_flag() -> None:
    sim = await ZWaveJsSim(schema=20).start()
    try:
        driver = await connected(zwave_file(sim))
        assert sim.chosen_schema == 20
        kernel = await kernel_for(driver)
        decision = await kernel.execute(Write(device="conformance-zwave", channel="level", value="40 percent"), WHO)
        assert decision.status == "done", decision.message
        await driver.close()
    finally:
        await sim.close()


async def test_refused_and_failed_values_are_driver_errors(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave))
    kernel = await kernel_for(driver)
    zwave.fail_next = 1
    decision = await kernel.execute(Write(device="conformance-zwave", channel="level", value="10 percent"), WHO)
    assert decision.status == "failed"
    assert "did not respond" in decision.message
    zwave.refuse_next = 1
    with pytest.raises(DriverError, match="zwave_error, The node did not acknowledge"):
        await driver.link.call({"command": "node.poll_value", "nodeId": 3, "valueId": {}})
    await driver.close()


async def test_dead_nodes_report_disconnected(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave))
    await zwave.kill(3)
    await wait_until(lambda: driver.link.status == 3)
    health = await driver.health()
    assert not health.connected
    assert "is dead" in health.detail
    await zwave.revive(3)
    await wait_until(lambda: driver.link.status == 4)
    assert (await driver.health()).connected
    await driver.close()


async def test_zwave_connection_problems(zwave: ZWaveJsSim) -> None:
    with pytest.raises(DriverError, match="has no node 9"):
        await connected(zwave_file(zwave, node=9))
    newer = await ZWaveJsSim(min_schema=45).start()
    try:
        with pytest.raises(DriverError, match="needs schema 45"):
            await connected(zwave_file(newer))
    finally:
        await newer.close()
    with pytest.raises(DriverError, match="Could not open zwave-js-server"):
        await connected(
            bare(
                "read:\n  x: { type: bool, map: { command_class: 37, property: currentValue } }",
                '{ zigbee-zwave: "ws://127.0.0.1:1", node: 2 }',
            )
        )


async def test_a_server_that_is_not_zwave_js_is_refused() -> None:
    from websockets.asyncio.server import serve

    async def chatty(connection: Any) -> None:
        await connection.send(json.dumps({"type": "hello"}))
        await connection.wait_closed()

    server = await serve(chatty, "127.0.0.1", 0)
    port = next(iter(server.sockets)).getsockname()[1]
    try:
        file = bare(
            "read:\n  x: { type: bool, map: { command_class: 37, property: currentValue } }",
            f'{{ zigbee-zwave: "ws://127.0.0.1:{port}", node: 2, timeout: 500 ms }}',
        )
        with pytest.raises(DriverError, match="isn't zwave-js-server"):
            await connected(file)
    finally:
        server.close()
        await server.wait_closed()


async def test_zwave_drops_and_slow_answers(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave))
    kernel = await kernel_for(driver)
    zwave.latency_s = 2.0
    decision = await kernel.execute(Write(device="conformance-zwave", channel="level", value="5 percent"), WHO)
    assert decision.status == "failed"
    assert "sent no reply to node.set_value" in decision.message
    zwave.latency_s = 0.0
    await zwave.drop()
    await wait_disconnected(driver)
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("level")
    await driver.close()


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        (
            "write:\n  power: { unit: W, min: 0, max: 1, map: { command_class: 50, property: value, "
            "property_key: 66049 } }",
            "can't be set",
        ),
        (
            "read:\n  motion: { type: enum, values: [running], map: { command_class: 113, property: Home Security, "
            "property_key: Motion sensor status } }",
            "doesn't list running",
        ),
        ("read:\n  x: { type: bool, map: { command_class: 99, property: nothing } }", "doesn't have this value"),
    ],
)
async def test_zwave_channels_are_checked(zwave: ZWaveJsSim, channels: str, message: str) -> None:
    node = 2 if "50" in channels else 4
    with pytest.raises(DriverError, match=message):
        await connected(zwave_file(zwave, node=node, channels=channels))


async def test_zwave_describe_proposes_values(zwave: ZWaveJsSim) -> None:
    driver = await connected(zwave_file(zwave, node=2, channels=PLUG))
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["current_value"]["map"] == {"command_class": 37, "endpoint": 0, "property": "currentValue"}
    assert proposal["read"]["electric_consumption__w"]["unit"] == "W"
    assert proposal["device"]["manufacturer"] == "Zooz"
    await driver.close()


async def test_the_zwave_conformance_case_passes(zwave: ZWaveJsSim) -> None:
    report = await run(zwave_case(zwave))
    failures = [f"{result.name}: {result.detail}" for result in report.results if not result.ok and not result.skipped]
    assert report.ok, failures


async def test_identify_before_connecting_names_the_target() -> None:
    driver = ZigbeeZWaveDriver(bare("read:\n  state: { type: bool }"))
    assert await driver.identify() == {"bridge": "zigbee2mqtt", "url": "mqtt://broker.local", "device": "lamp"}
    assert not (await driver.health()).connected


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    ZigbeeZWaveDriver(report.file)
