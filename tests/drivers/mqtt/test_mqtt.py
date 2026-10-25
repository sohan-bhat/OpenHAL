"""The mqtt driver, with a real paho-mqtt client against the in-process MQTT 3.1.1 broker."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.mqtt.conformance import device_file, wait_until
from openhal.drivers.mqtt.driver import MqttDriver, describe_topics
from openhal.drivers.mqtt.simulator import MqttBroker, SimulatedFan, topic_matches
from openhal.kernel import Kernel
from openhal.kernel.commands import Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "mqtt" / "examples"
WHO = human("tester")


@pytest.fixture
def broker() -> Iterator[MqttBroker]:
    with MqttBroker() as running:
        yield running


@pytest.fixture
def fan(broker: MqttBroker) -> SimulatedFan:
    return SimulatedFan(broker).attach()


def file_for(broker: MqttBroker, channels: str, extra: str = "") -> DeviceFile:
    connect = f"{{ mqtt: 127.0.0.1, port: {broker.port}, timeout: 1 s{extra} }}"
    return loads(
        f"device: T\nid: t\nconnect: {connect}\n{channels}\nhazard: low\nconfirmed: {{ by: t, at: 2026-10-24 }}\n"
    )


async def connected(file: DeviceFile, **kwargs: object) -> MqttDriver:
    driver = MqttDriver(file, **kwargs)  # type: ignore[arg-type]
    await driver.connect()
    return driver


async def kernel_for(driver: MqttDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = "{ mqtt: broker.local }") -> DeviceFile:
    return loads(f"device: T\nconnect: {connect}\n{channels}\n")


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ("{ mqtt: b, token_env: secret }", "pattern"),
        ("{ mqtt: b, client_id: aaaaaaaaaaaaaaaaaaaaaaaaaaaa }", "at most 23"),
        ("{ mqtt: b, qos: 2 }", "0 or 1"),
        ("{ mqtt: b, keepalive: 1 }", "greater than or equal to 5"),
        ("{ mqtt: b, colour: red }", "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        MqttDriver(bare("read:\n  x: { unit: W, map: { state: a } }", connect))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { unit: W }", "needs a map"),
        ("read:\n  x: { unit: W, map: { state: 'a/+/b' } }", "wildcard"),
        ("read:\n  x: { unit: W, map: { state: 'a/#' } }", "wildcard"),
        ("read:\n  x: { unit: W, map: { state: a, json: '$..x' } }", "invalid key"),
        ("read:\n  x: { unit: W, map: { state: a, scale: 0 } }", "zero"),
        ("read:\n  x: { type: image }", "image"),
        ("write:\n  x: { type: bool, map: { state: a } }", "command"),
        ("write:\n  x: { type: bool, map: { command: a, template: { v: '{other}' } } }", "only use"),
        ("actions:\n  go: {}", "no actions"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MqttDriver(bare(channels))


def test_topic_matching() -> None:
    assert topic_matches("a/+/c", "a/b/c")
    assert topic_matches("a/#", "a/b/c")
    assert topic_matches("#", "a")
    assert not topic_matches("a/+", "a/b/c")
    assert not topic_matches("a/b", "a")


async def test_retained_state_seeds_every_read(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = await connected(device_file(broker))
    temperature = await driver.read("temperature")
    assert temperature.value == pytest.approx(24.5)
    assert temperature.unit == "degC"
    assert (await driver.read("humidity")).value == pytest.approx(41.0)
    assert (await driver.read("speed")).value == 0.0
    assert (await driver.read("power")).value is False
    assert (await driver.read("mode")).value == "auto"
    await driver.close()


async def test_streamed_updates_replace_the_cached_value(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = await connected(device_file(broker))
    first = await driver.read("temperature")
    broker.publish("lab/fan/sensor", json.dumps({"climate": {"temperature": 30.25, "humidity": 50}}))
    await wait_until(lambda: driver._latest["lab/fan/sensor"][0].startswith(b'{"climate": {"temperature": 30'))
    second = await driver.read("temperature")
    assert second.value == pytest.approx(30.25)
    assert second.at >= first.at
    await driver.close()


async def test_unknown_until_first_message(broker: MqttBroker) -> None:
    driver = await connected(file_for(broker, "read:\n  quiet: { unit: W, map: { state: nothing/here } }"))
    reading = await driver.read("quiet")
    assert reading.value is None
    assert reading.unit == "W"
    broker.publish("nothing/here", "12.5")
    await wait_until(lambda: "nothing/here" in driver._latest)
    assert (await driver.read("quiet")).value == 12.5


async def test_payload_formats_words_scale_prefix_and_range(broker: MqttBroker) -> None:
    channels = (
        "read:\n"
        "  level: { unit: percent, range: [0, 50], map: { state: lamp/state, format: json, json: brightness,"
        " scale: 0.3937008 } }\n"
        "  on: { type: bool, map: { state: lamp/state, format: json, json: state } }\n"
        "  door: { type: bool, map: { state: door, on: open, off: shut } }\n"
        "  raw: { unit: degC, map: { state: temp, offset: -273.15 } }"
    )
    broker.publish("home/lamp/state", json.dumps({"state": "ON", "brightness": 254}), retain=True)
    broker.publish("home/door", "open", retain=True)
    broker.publish("home/temp", "300", retain=True)
    driver = await connected(file_for(broker, channels, ", prefix: home/"))
    level = await driver.read("level")
    assert level.value == pytest.approx(100.0, rel=1e-4)
    assert level.suspect is True
    assert (await driver.read("on")).value is True
    assert (await driver.read("door")).value is True
    assert (await driver.read("raw")).value == pytest.approx(26.85)


async def test_malformed_payloads_raise(broker: MqttBroker) -> None:
    channels = (
        "read:\n"
        "  num: { unit: W, map: { state: num } }\n"
        "  doc: { unit: W, map: { state: doc, format: json, json: a.b } }\n"
        "  flag: { type: bool, map: { state: flag } }\n"
        "  mode: { type: enum, values: [a, b], map: { state: mode } }"
    )
    for topic, payload in (("num", "hello"), ("doc", "{not json"), ("flag", "maybe"), ("mode", "c")):
        broker.publish(topic, payload, retain=True)
    driver = await connected(file_for(broker, channels))
    with pytest.raises(DriverError, match="not a number"):
        await driver.read("num")
    with pytest.raises(DriverError, match="not JSON"):
        await driver.read("doc")
    with pytest.raises(DriverError, match="neither an on word"):
        await driver.read("flag")
    with pytest.raises(DriverError, match="not one of a, b"):
        await driver.read("mode")
    broker.publish("doc", '{"a": {}}', retain=True)
    await wait_until(lambda: driver._latest["doc"][0] == b'{"a": {}}')
    with pytest.raises(DriverError, match=r"no field \$\.a\.b"):
        await driver.read("doc")


async def test_reads_need_a_connection(broker: MqttBroker) -> None:
    driver = MqttDriver(device_file(broker))
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("speed")
    with pytest.raises(DriverError, match="no channel"):
        await driver.read("nope")


async def test_commands_reach_the_device_and_state_follows(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = MqttDriver(device_file(broker))
    kernel = await kernel_for(driver)
    for channel, value in (("speed", "42 %"), ("power", True), ("mode", "eco")):
        decision = await kernel.execute(Write(device="conformance-mqtt", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    assert (fan.speed, fan.power, fan.mode) == (42.0, True, "eco")
    sent = [(topic, payload, qos) for topic, payload, qos, _ in broker.published]
    assert ("lab/fan/speed/set", b"42", 1) in sent
    assert ("lab/fan/power/set", b"ON", 1) in sent
    assert ("lab/fan/mode/set", b'{"mode":"eco"}', 1) in sent
    await wait_until(lambda: driver._latest["lab/fan/power"][0] == b"ON")
    assert (await driver.read("power")).value is True
    await driver.close()


async def test_templates_words_qos_retain_and_scale(broker: MqttBroker) -> None:
    channels = (
        "write:\n"
        "  lamp: { type: bool, map: { command: z2m/lamp/set, template: { state: '{value}', transition: 2 },"
        " on: 'ON', off: 'OFF', qos: 0 } }\n"
        "  level: { unit: percent, min: 0, max: 100, map: { command: z2m/lamp/set, format: json, json: brightness,"
        " scale: 0.3937008, retain: true } }\n"
        "  relay: { type: bool, map: { command: relay/set, on: 1, off: 0 } }"
    )
    driver = MqttDriver(file_for(broker, channels))
    kernel = await kernel_for(driver)
    assert (await driver.read("lamp")).value is None
    await kernel.execute(Write(device="t", channel="lamp", value=True), WHO)
    await kernel.execute(Write(device="t", channel="level", value="100 %"), WHO)
    await kernel.execute(Write(device="t", channel="relay", value=False), WHO)
    published = broker.published
    assert ("z2m/lamp/set", b'{"state":"ON","transition":2}', 0, False) in published
    assert ("z2m/lamp/set", b'{"brightness":254}', 1, True) in published
    assert ("relay/set", b"0", 1, False) in published
    assert (await driver.read("lamp")).value is True


async def test_disconnected_writes_fail_and_are_never_queued(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = MqttDriver(device_file(broker))
    kernel = await kernel_for(driver)
    broker.kick_all()
    await wait_until(lambda: not driver.connected)
    before = len(broker.published)
    decision = await kernel.execute(Write(device="conformance-mqtt", channel="power", value=True), WHO)
    assert decision.status in ("failed", "blocked")
    await driver.connect()
    await wait_until(lambda: driver.connected)
    assert len(broker.published) == before
    assert fan.power is False


async def test_missing_puback_times_out_and_drops_the_client(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = MqttDriver(device_file(broker, timeout="0.3 s"))
    kernel = await kernel_for(driver)
    broker.hold_acks = True
    decision = await kernel.execute(Write(device="conformance-mqtt", channel="power", value=True), WHO)
    assert decision.status == "failed"
    assert "didn't acknowledge" in decision.message
    assert (await driver.health()).connected is False


async def test_no_broker_fails_to_connect() -> None:
    broker = MqttBroker()
    driver = MqttDriver(device_file(broker))
    with pytest.raises(DriverError, match="Could not reach"):
        await driver.connect()
    assert (await driver.health()).connected is False


async def test_credentials(broker: MqttBroker) -> None:
    broker.username, broker.password = "openhal", "hunter2"
    file = device_file(broker, extra=", username: openhal, token_env: MQTT_PASSWORD")
    with pytest.raises(DriverError, match="MQTT_PASSWORD is not set"):
        await connected(file, environ=lambda name: None)
    with pytest.raises(DriverError, match="did not accept the connection"):
        await connected(file, environ=lambda name: "wrong")
    driver = await connected(file, environ=lambda name: "hunter2")
    assert (await driver.health()).connected
    await driver.close()


async def test_dropped_connection_is_noticed_and_reconnects(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = await connected(device_file(broker))
    assert (await driver.health()).connected
    broker.kick_all()
    await wait_until(lambda: not driver.connected)
    health = await driver.health()
    assert health.connected is False
    assert "disconnected" in health.detail
    fan.speed = 10
    fan.publish_all()
    await driver.connect()
    assert (await driver.read("speed")).value == 10.0
    assert broker.connections == 2
    await driver.close()


async def test_identify_and_discover(broker: MqttBroker) -> None:
    driver = MqttDriver(device_file(broker))
    identity = await driver.identify()
    assert identity["broker"] == f"127.0.0.1:{broker.port}"
    assert identity["client_id"].startswith("oh-conformance-m-")
    assert len(identity["client_id"]) == 23
    other = MqttDriver(loads(device_file(broker).model_dump_json().replace("conformance-mqtt", "conformance-mqtt-2")))
    assert (await other.identify())["client_id"] != identity["client_id"]
    assert await MqttDriver.discover() == []


async def test_describe_listens_and_proposes_reads(broker: MqttBroker, fan: SimulatedFan) -> None:
    driver = MqttDriver(device_file(broker))
    assert await driver.describe() is None
    await driver.connect()
    described = await driver.describe(listen_s=0.3)
    assert described is not None
    reads = described["read"]
    assert reads["lab_fan_speed"] == {"unit": "dimensionless", "map": {"state": "lab/fan/speed"}}
    assert reads["lab_fan_power"] == {"type": "bool", "map": {"state": "lab/fan/power"}}
    assert "lab_fan_sensor_climate" not in reads
    loads_ok = DeviceFile.model_validate({"device": "x", "connect": {"mqtt": "b"}, "read": reads})
    MqttDriver(loads_ok)
    await driver.close()


def test_describe_topics_handles_objects_and_limits() -> None:
    seen = {
        "p/a": b'{"t": 1.5, "on": true, "name": "x", "bad key": 1}',
        "p/b": b"OFF",
        "p/c": b"<html>",
        "p/1": b"7",
    }
    described = describe_topics(seen, prefix="p/")
    assert set(described["read"]) == {"a_t", "a_on", "b", "ch_1"}
    assert described["read"]["a_t"]["map"] == {"state": "a", "format": "json", "json": "$.t"}
    assert "read" not in describe_topics({})


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    MqttDriver(report.file)
