"""The matter driver, against the simulated Matter Server WebSocket API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.matter.conformance import device_file
from openhal.drivers.matter.driver import MatterDriver
from openhal.drivers.matter.simulator import MatterServerSim
from openhal.drivers.mqtt.conformance import wait_until
from openhal.kernel import Kernel
from openhal.kernel.commands import Action, Write
from openhal.kernel.principals import human
from openhal.spec import loads, validate_path
from openhal.spec.models import DeviceFile

EXAMPLES = Path(__file__).parents[3] / "openhal" / "drivers" / "matter" / "examples"
WHO = human("tester")
SENSOR = """
read:
  temperature: { unit: degC, range: [-10, 40], map: { path: 1/1026/0, scale: 0.01 } }
  humidity: { unit: percent, map: { path: 1/1029/0, scale: 0.01 } }
  battery: { unit: percent, map: { path: 1/47/12, scale: 0.5 } }
  vendor: { type: string, map: { path: 0/40/1 } }
"""
THERMOSTAT = """
read:
  room: { unit: degF, map: { path: 1/513/0, scale: 0.01, unit: degC } }
write:
  heating_setpoint: { unit: degC, min: 5, max: 40, map: { path: 1/513/18, scale: 0.01 } }
hazard: low
confirmed: { by: t, at: 2026-10-24 }
"""


@pytest.fixture
async def server() -> AsyncIterator[MatterServerSim]:
    sim = await MatterServerSim().start()
    yield sim
    await sim.close()


async def connected(file: DeviceFile) -> MatterDriver:
    driver = MatterDriver(file)
    await driver.connect()
    return driver


async def kernel_for(driver: MatterDriver) -> Kernel:
    kernel = Kernel()
    kernel.register(driver.device, driver)
    await kernel.connect(driver.device.device_id)
    return kernel


def bare(channels: str, connect: str = '{ matter: "ws://server.local:5580/ws", node: 5 }') -> DeviceFile:
    return loads(f"device: T\nid: t\nconnect: {connect}\n{channels}\n")


@pytest.mark.parametrize(
    ("connect", "message"),
    [
        ('{ matter: "http://server:5580/ws", node: 5 }', "pattern"),
        ('{ matter: "ws://server:5580/ws" }', "node"),
        ('{ matter: "ws://server:5580/ws", node: 0 }', "greater than or equal to 1"),
        ('{ matter: "ws://server:5580/ws", node: 5, colour: red }', "Extra inputs"),
    ],
)
def test_bad_params(connect: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        MatterDriver(bare("read:\n  x: { type: bool, map: { path: 1/6/0 } }", connect))


@pytest.mark.parametrize(
    ("channels", "message"),
    [
        ("read:\n  x: { type: bool }", "needs a map"),
        ("read:\n  x: { type: bool, map: { path: 1-6-0 } }", "endpoint/cluster/attribute"),
        ("read:\n  x: { type: bool, map: { path: 1/6/0, endpoint: 1 } }", "not both"),
        ("read:\n  x: { type: bool, map: { endpoint: 1, cluster: 6 } }", "name the attribute"),
        ("read:\n  x: { type: enum, values: [a], map: { path: 1/257/0 } }", "needs map.lookup"),
        ("read:\n  x: { unit: percent, map: { path: 1/1030/0, bit: 0 } }", "needs type bool"),
        ("read:\n  x: { unit: degC, map: { path: 1/1026/0, unit: V } }", "doesn't convert"),
        ("read:\n  x: { type: image, map: { path: 1/6/0 } }", "not images"),
        ("write:\n  x: { type: bool, map: { path: 1/6/0, on_command: On } }", "both on_command"),
        (
            "write:\n  x: { unit: percent, min: 0, max: 1, map: { path: 1/8/0, on_command: On, off_command: Off } }",
            "for bool channels",
        ),
        (
            "write:\n  x: { unit: percent, min: 0, max: 1, map: { path: 1/8/0, command: MoveToLevel, "
            "payload: { level: 3 } } }",
            "needs a {value}",
        ),
        (
            "write:\n  x: { unit: percent, min: 0, max: 1, map: { path: 1/8/0, command: MoveToLevel, "
            "payload: { level: '{value}', other: '{x}' } } }",
            "only use {value}",
        ),
        (
            "actions:\n  identify: { args: { seconds: { unit: s, min: 1, max: 9 } }, map: { endpoint: 1, cluster: 3, "
            "command: Identify } }",
            "every argument",
        ),
        ("write:\n  x: { type: bool, map: { path: 1/6/0, command: on } }", "pattern"),
    ],
)
def test_bad_maps(channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MatterDriver(bare(channels))


async def test_reads_come_from_the_subscription(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    level = await driver.read("level")
    assert level.value == pytest.approx(50.0)
    assert level.unit == "percent"
    assert (await driver.read("power")).value is False
    assert (await driver.read("identify_time")).value == 0.0
    identity = await driver.identify()
    assert (identity["vendor"], identity["product"], identity["serial"]) == ("Nanoleaf", "Essentials A19", "NL67A1B2C3")
    assert identity["sdk"] == "2025.7.0"
    await server.set_attribute(5, "1/8/0", 254)
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/8/0"] == 254)
    assert (await driver.read("level")).value == pytest.approx(100.0)
    await driver.close()


async def test_scaled_sensor_values(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url, node=6, channels=SENSOR))
    assert (await driver.read("temperature")).value == pytest.approx(21.54)
    assert (await driver.read("humidity")).value == pytest.approx(48.2)
    assert (await driver.read("battery")).value == pytest.approx(91.0)
    assert (await driver.read("vendor")).value == "Eve Systems"
    await server.set_attribute(6, "1/1026/0", 4550)
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/1026/0"] == 4550)
    hot = await driver.read("temperature")
    assert hot.suspect
    await server.set_attribute(6, "1/1026/0", None)
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/1026/0"] is None)
    assert (await driver.read("temperature")).value is None
    await driver.close()


async def test_commands_run_cluster_commands(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    kernel = await kernel_for(driver)
    for channel, value in (("power", True), ("level", "40 percent"), ("power", False)):
        decision = await kernel.execute(Write(device="conformance-matter", channel=channel, value=value), WHO)
        assert decision.status == "done", decision.message
    commands = [call["args"] for call in server.calls if call["command"] == "device_command"]
    assert [(args["command_name"], args["payload"]) for args in commands] == [
        ("On", {}),
        ("MoveToLevelWithOnOff", {"level": 102, "transitionTime": 0, "optionsMask": 0, "optionsOverride": 0}),
        ("Off", {}),
    ]
    assert commands[0]["node_id"] == 5
    assert (commands[0]["endpoint_id"], commands[0]["cluster_id"]) == (1, 6)
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/6/0"] is False)
    assert (await driver.read("level")).value == pytest.approx(40.2, abs=0.1)
    await driver.close()


async def test_actions_fill_the_payload(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    kernel = await kernel_for(driver)
    decision = await kernel.execute(
        Action(device="conformance-matter", action="identify", args={"seconds": "5 s"}), WHO
    )
    assert decision.status == "done", decision.message
    call = server.calls[-1]
    assert (call["args"]["command_name"], call["args"]["payload"]) == ("Identify", {"identifyTime": 5})
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/3/0"] == 5)
    assert (await driver.read("identify_time")).value == 5.0
    await driver.close()


async def test_attribute_writes_and_their_status(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url, node=7, channels=THERMOSTAT))
    assert (await driver.read("room")).value == pytest.approx(68.9)
    kernel = await kernel_for(driver)
    decision = await kernel.execute(
        Write(device="conformance-matter", channel="heating_setpoint", value="21.5 degC"), WHO
    )
    assert decision.status == "done", decision.message
    write = server.calls[-1]
    assert write["command"] == "write_attribute"
    assert write["args"] == {"node_id": 7, "attribute_path": "1/513/18", "value": 2150}
    await wait_until(lambda: driver.client is not None and driver.client.attributes["1/513/18"] == 2150)
    assert (await driver.read("heating_setpoint")).value == pytest.approx(21.5)
    decision = await kernel.execute(
        Write(device="conformance-matter", channel="heating_setpoint", value="35 degC"), WHO
    )
    assert decision.status == "failed"
    assert "CONSTRAINT_ERROR" in decision.message
    await driver.close()


async def test_server_errors_are_driver_errors(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    kernel = await kernel_for(driver)
    server.fail_next = 1
    decision = await kernel.execute(Write(device="conformance-matter", channel="power", value=True), WHO)
    assert decision.status == "failed"
    assert "SDK stack error, Chip Stack Error" in decision.message
    assert driver.client is not None
    with pytest.raises(DriverError, match="invalid command"):
        await driver.client.call("open_the_pod_bay_doors")
    await driver.close()


async def test_unavailable_nodes(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    await server.unavailable(5)
    await wait_until(lambda: driver.client is not None and not driver.client.available)
    health = await driver.health()
    assert not health.connected
    assert "unavailable" in health.detail
    with pytest.raises(DriverError, match="unavailable"):
        await driver.read("power")
    await server.available(5)
    await wait_until(lambda: driver.client is not None and driver.client.available)
    assert (await driver.health()).connected
    await driver.close()


async def test_a_dropped_server_is_reported_and_reconnects(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    await server.drop()
    await wait_until(lambda: driver.client is not None and not driver.client.connected)
    health = await driver.health()
    assert not health.connected
    assert "closed" in health.detail or "failed" in health.detail
    with pytest.raises(DriverError, match="not connected"):
        await driver.read("power")
    await driver.connect()
    assert (await driver.read("power")).value is False
    await driver.close()
    assert not (await driver.health()).connected
    assert await driver.describe() is None


async def test_slow_answers_time_out(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url, timeout="300 ms"))
    kernel = await kernel_for(driver)
    server.latency_s = 1.0
    decision = await kernel.execute(Write(device="conformance-matter", channel="power", value=True), WHO)
    assert decision.status == "failed"
    assert "didn't answer device_command" in decision.message
    server.latency_s = 0.0
    await driver.close()


@pytest.mark.parametrize(
    ("node", "channels", "message"),
    [
        (5, "read:\n  x: { type: bool, map: { path: 1/1030/0, bit: 0 } }", "no attribute 1/1030/0"),
        (6, "actions:\n  identify: { map: { endpoint: 1, cluster: 3, command: Identify } }", "no cluster 3"),
        (9, "read:\n  x: { type: bool, map: { path: 1/6/0 } }", "has no node 9"),
    ],
)
async def test_the_node_is_checked_on_connect(server: MatterServerSim, node: int, channels: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        await connected(device_file(server.url, node=node, channels=channels))


async def test_servers_that_are_not_matter_servers(server: MatterServerSim) -> None:
    old = await MatterServerSim(schema=3).start()
    try:
        with pytest.raises(DriverError, match="Update it to 5"):
            await connected(device_file(old.url))
    finally:
        await old.close()
    from websockets.asyncio.server import serve

    async def other(connection: Any) -> None:
        await connection.send(json.dumps({"type": "version"}))
        await connection.wait_closed()

    imposter = await serve(other, "127.0.0.1", 0)
    port = next(iter(imposter.sockets)).getsockname()[1]
    try:
        with pytest.raises(DriverError, match="isn't a Matter Server"):
            await connected(device_file(f"ws://127.0.0.1:{port}/ws"))
    finally:
        imposter.close()
        await imposter.wait_closed()
    with pytest.raises(DriverError, match="Could not open the Matter Server"):
        await connected(device_file("ws://127.0.0.1:1/ws"))


async def test_removed_nodes_end_the_session(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    await server._event("node_removed", 5)
    await wait_until(lambda: driver.client is not None and not driver.client.connected)
    assert "removed" in (await driver.health()).detail
    await driver.close()


async def test_describe_proposes_known_clusters(server: MatterServerSim) -> None:
    driver = await connected(device_file(server.url))
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["power"]["map"]["on_command"] == "On"
    assert proposal["write"]["level"]["suggested"] is True
    assert proposal["device"] == {"name": "Essentials A19", "manufacturer": "Nanoleaf"}
    await driver.close()
    sensor = await connected(device_file(server.url, node=6, channels=SENSOR))
    proposal = await sensor.describe()
    assert proposal is not None
    assert set(proposal["read"]) == {"temperature", "humidity", "battery"}
    assert "write" not in proposal
    await sensor.close()


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.hal.yaml")), ids=lambda path: path.name)
def test_examples_validate_and_load_read_only(path: Path) -> None:
    report = validate_path(path)
    assert report.ok, report.problems
    assert report.file is not None
    assert not report.file.writable
    MatterDriver(report.file)
