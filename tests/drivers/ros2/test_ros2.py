"""The ROS 2 driver, against the simulated rosbridge server on a local WebSocket."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.ros2 import channels
from openhal.drivers.ros2.driver import Ros2Driver
from openhal.drivers.ros2.simulator import RosbridgeSim
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

ROBOT = """
device: Test turtle
id: turtle
connect: {{ ros2: 127.0.0.1, port: {port}, timeout: 500 ms, action_wait: 2 s }}
read:
  battery:
    unit: percent
    range: [0, 100]
    map: {{ topic: /battery_state, type: sensor_msgs/msg/BatteryState, field: percentage, unit: dimensionless }}
  cell_1: {{ unit: mV, map: {{ topic: /battery_state, field: cell_voltage.1, unit: V }} }}
  odom_x: {{ unit: cm, map: {{ topic: /odom, type: nav_msgs/msg/Odometry, field: pose.pose.position.x, unit: m }} }}
  lamp_on: {{ type: bool, map: {{ topic: /lamp_state, field: data }} }}
  mode: {{ type: enum, values: [auto, manual], map: {{ topic: /mode, field: data }} }}
write:
  drive:
    unit: m/s
    min: -0.3
    max: 0.3
    map:
      topic: /cmd_vel
      type: geometry_msgs/msg/Twist
      field: linear.x
      unit: m/s
      base: {{ linear: {{ x: 0, y: 0, z: 0 }}, angular: {{ x: 0, y: 0, z: 0 }} }}
  lamp: {{ type: bool, map: {{ service: /set_lamp, type: std_srvs/srv/SetBool, field: data }} }}
actions:
  reset_odometry: {{ map: {{ service: /reset_odometry, type: std_srvs/srv/Trigger }} }}
  navigate:
    args: {{ x: {{ unit: m, min: -5, max: 5 }}, y: {{ unit: m, min: -5, max: 5 }} }}
    map: {{ action: /navigate, type: turtle_msgs/action/Navigate, args: {{ x: x, y: y }} }}
  flash: {{ map: {{ topic: /lamp, type: std_msgs/msg/Bool, base: {{ data: true }} }} }}
safe_state: {{ drive: 0 }}
hazard: high
confirmed: {{ by: tester, at: 2026-10-24 }}
"""


@pytest.fixture
async def robot() -> AsyncIterator[RosbridgeSim]:
    sim = RosbridgeSim()
    sim.time_scale = 10
    await sim.start()
    yield sim
    await sim.stop()


def make(sim: RosbridgeSim, text: str = ROBOT) -> tuple[Ros2Driver, Bench]:
    file = loads(text.format(port=sim.port))
    driver = Ros2Driver(file)
    return driver, Bench(file, driver)


async def _arrived(driver: Ros2Driver, topic: str) -> bool:
    return driver.bridge is not None and topic in driver.bridge.latest


async def test_connect_subscribes_once_per_topic_and_advertises_what_it_publishes(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    await eventually(lambda: asyncio.sleep(0, len(robot.ops("advertise")) == 2))
    subscribed = sorted(item["topic"] for item in robot.ops("subscribe"))
    assert subscribed == ["/battery_state", "/lamp_state", "/mode", "/odom"]
    battery = next(item for item in robot.ops("subscribe") if item["topic"] == "/battery_state")
    assert battery["type"] == "sensor_msgs/msg/BatteryState"
    assert sorted(item["topic"] for item in robot.ops("advertise")) == ["/cmd_vel", "/lamp"]
    identity = await driver.identify()
    assert (identity["distro"], identity["nodes"]) == ("jazzy", "3")
    health = await driver.health()
    assert health.connected
    assert health.latency_ms is not None
    await bench.close()


async def test_topic_fields_with_units_and_types(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    await eventually(lambda: _arrived(driver, "/mode"))
    assert (await bench.read("battery")).value == pytest.approx(87.0)
    assert (await bench.read("cell_1")).value == pytest.approx(4100.0)
    assert (await bench.read("odom_x")).value == pytest.approx(0.0)
    assert (await bench.read("lamp_on")).value is False
    assert (await bench.read("mode")).value == "auto"
    robot.battery = 1.5
    await eventually(lambda: _suspect(bench, "battery"))
    await bench.close()


async def _suspect(bench: Bench, channel: str) -> bool:
    return (await bench.read(channel)).suspect


async def test_reads_are_unknown_until_a_message_arrives(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    assert driver.bridge is not None
    driver.bridge.latest.clear()
    reading = await driver.read("battery")
    assert reading.value is None
    await bench.close()


async def test_publishing_a_velocity_moves_the_robot(robot: RosbridgeSim) -> None:
    _driver, bench = make(robot)
    await bench.connect()
    assert_done(await bench.write("drive", "20 cm/s"))
    await eventually(lambda: asyncio.sleep(0, bool(robot.ops("publish"))))
    sent = robot.ops("publish")[-1]
    assert sent["topic"] == "/cmd_vel"
    assert sent["msg"] == {"linear": {"x": pytest.approx(0.2), "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}
    assert (await bench.read("drive")).value == pytest.approx(0.2)
    await eventually(lambda: asyncio.sleep(0, robot.x > 0.05))
    assert await bench.stop() == "safe"
    await eventually(lambda: asyncio.sleep(0, robot.linear == 0.0))
    await bench.close()


async def test_service_change_and_service_failure(robot: RosbridgeSim) -> None:
    _driver, bench = make(robot)
    await bench.connect()
    assert_done(await bench.write("lamp", True))
    assert robot.lamp is True
    call = robot.ops("call_service")[-1]
    assert (call["service"], call["args"], call["type"]) == ("/set_lamp", {"data": True}, "std_srvs/srv/SetBool")
    assert (await bench.read("lamp")).value is True
    text = ROBOT.replace("service: /set_lamp", "service: /set_lamb")
    _other, other_bench = make(robot, text)
    await other_bench.connect()
    assert_failed(await other_bench.write("lamp", False), "does not exist")
    assert (await other_bench.read("lamp")).value is None
    await other_bench.close()
    await bench.close()


async def test_trigger_service_and_topic_actions(robot: RosbridgeSim) -> None:
    _driver, bench = make(robot)
    await bench.connect()
    robot.x = 3.0
    assert_done(await bench.act("reset_odometry"))
    assert robot.x == 0.0
    assert_done(await bench.act("flash"))
    await eventually(lambda: asyncio.sleep(0, robot.lamp))
    await bench.close()


async def test_navigate_goal_finishes(robot: RosbridgeSim) -> None:
    _driver, bench = make(robot)
    await bench.connect()
    decision = await bench.act("navigate", x="1 m", y="200 cm")
    assert_done(decision)
    goal = robot.ops("send_action_goal")[-1]
    assert (goal["action"], goal["action_type"], goal["args"]) == (
        "/navigate",
        "turtle_msgs/action/Navigate",
        {"x": 1.0, "y": 2.0},
    )
    assert (robot.x, robot.y) == (1.0, 2.0)
    await bench.close()


async def test_long_goal_starts_and_a_stop_cancels_it(robot: RosbridgeSim) -> None:
    text = ROBOT.replace("action_wait: 2 s", "action_wait: 200 ms")
    driver, bench = make(robot, text)
    await bench.connect()
    robot.time_scale = 1
    robot.navigate_s = 60
    assert_done(await bench.act("navigate", x="1 m", y="1 m"))
    assert driver.bridge is not None
    assert len(driver.bridge.goals) == 1
    assert "1 goals running" in (await driver.health()).detail
    assert await bench.stop() == "safe"
    assert robot.ops("cancel_action_goal")
    assert not robot.goals
    assert not driver.bridge.goals
    await bench.close()


async def test_refused_goal_and_bad_publish(robot: RosbridgeSim) -> None:
    text = ROBOT.replace("args: {{ x: x, y: y }}", "args: {{ x: target.x, y: target.y }}")
    _driver, bench = make(robot, text)
    await bench.connect()
    assert_failed(await bench.act("navigate", x="1 m", y="1 m"), "aborted")
    await bench.close()
    text = ROBOT.replace("action: /navigate,", "action: /fly,")
    _driver, bench = make(robot, text)
    await bench.connect()
    assert_failed(await bench.act("navigate", x="1 m", y="1 m"), "no action server /fly")
    await bench.close()


async def test_type_mismatch_is_reported_by_rosbridge(robot: RosbridgeSim) -> None:
    text = ROBOT.replace("type: sensor_msgs/msg/BatteryState", "type: std_msgs/msg/Float32")
    driver, bench = make(robot, text)
    await bench.connect()
    assert driver.bridge is not None
    bridge = driver.bridge
    await eventually(lambda: asyncio.sleep(0, "/battery_state" in bridge.refused))
    with pytest.raises(DriverError, match="refused the subscription to /battery_state"):
        await driver.read("battery")
    assert "already has type" in (await driver.health()).detail
    await bench.close()


async def test_missing_field_and_wrong_value_types(robot: RosbridgeSim) -> None:
    text = ROBOT.replace("field: cell_voltage.1", "field: cell_voltage.7").replace(
        "  mode: {{", "  mode_bad: {{ unit: V, map: {{ topic: /mode, field: data }} }}\n  mode: {{"
    )
    driver, bench = make(robot, text)
    await bench.connect()
    await eventually(lambda: _arrived(driver, "/mode"))
    await eventually(lambda: _arrived(driver, "/battery_state"))
    with pytest.raises(DriverError, match=r"has no field cell_voltage\.7"):
        await driver.read("cell_1")
    with pytest.raises(DriverError, match="expected a finite number"):
        await driver.read("mode_bad")
    await bench.close()


async def test_lost_connection_and_reconnect(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    robot.drop_clients()
    await eventually(lambda: _disconnected(driver))
    with pytest.raises(DriverError, match="connection was lost"):
        await driver.read("battery")
    await bench.connect()
    await eventually(lambda: _arrived(driver, "/battery_state"))
    assert (await bench.read("battery")).value == pytest.approx(87.0)
    await bench.close()


async def _disconnected(driver: Ros2Driver) -> bool:
    return not (await driver.health()).connected


async def test_non_json_from_rosbridge_drops_the_connection(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    robot.inject("this is not json")
    await eventually(lambda: _disconnected(driver))
    assert driver.bridge is not None
    assert driver.bridge.lost == "rosbridge sent a message that is not JSON"
    await bench.close()


async def test_silent_rosbridge_times_out(robot: RosbridgeSim) -> None:
    _driver, bench = make(robot)
    await bench.connect()
    robot.silent = True
    assert_failed(await bench.act("reset_odometry"), "didn't answer")
    robot.silent = False
    await bench.close()


async def test_unreachable_rosbridge() -> None:
    driver = Ros2Driver(loads("device: Robot\nid: robot\nconnect: { ros2: 127.0.0.1, port: 9, timeout: 300 ms }\n"))
    with pytest.raises(DriverError, match="Could not reach rosbridge"):
        await driver.connect()
    assert not (await driver.health()).connected
    assert await driver.describe() is None
    assert await driver.identify() == {"rosbridge": "ws://127.0.0.1:9"}


async def test_describe_proposes_channels_from_rosapi(robot: RosbridgeSim) -> None:
    driver, bench = make(robot)
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["read"]["battery_state_percentage"]["map"] == {
        "topic": "/battery_state",
        "type": "sensor_msgs/msg/BatteryState",
        "field": "percentage",
        "unit": "dimensionless",
    }
    assert proposal["read"]["odom_x"]["unit"] == "m"
    assert proposal["write"]["cmd_vel_linear"]["max"] == 0.2
    assert all(entry["suggested"] for entry in proposal["write"].values())
    assert all(entry["suggested"] for entry in proposal["actions"].values())
    assert proposal["actions"]["set_lamp"]["args"] == {"data": {"type": "bool"}}
    assert proposal["safe_state"] == [{"cmd_vel_linear": 0, "cmd_vel_angular": 0}]
    assert "/navigate" in proposal["notes"]
    assert "rosout" not in proposal["notes"]
    assert "get_parameters" not in proposal["notes"]
    await bench.close()


def test_field_paths() -> None:
    message = {"pose": {"position": {"x": 1.5}}, "ranges": [0.1, 0.2]}
    assert channels.get_field(message, "pose.position.x") == 1.5
    assert channels.get_field(message, "ranges.1") == 0.2
    with pytest.raises(KeyError):
        channels.get_field(message, "ranges.9")
    with pytest.raises(KeyError):
        channels.get_field(message, "pose.velocity")
    built = channels.with_field({"linear": {"y": 0}}, "linear.x", 0.5)
    assert built == {"linear": {"y": 0, "x": 0.5}}
    assert channels.with_field({"data": [1, 2]}, "data.1", 9) == {"data": [1, 9]}
    with pytest.raises(DriverError, match="is not an object"):
        channels.with_field({"linear": 3}, "linear.x", 1)


async def test_integer_fields_take_whole_numbers(robot: RosbridgeSim) -> None:
    text = ROBOT.replace(
        "  lamp: {{ type: bool",
        "  level: {{ unit: dimensionless, min: 0, max: 10,\n"
        "    map: {{ topic: /lamp, type: std_msgs/msg/Bool, field: level, integer: true }} }}\n  lamp: {{ type: bool",
    )
    _driver, bench = make(robot, text)
    await bench.connect()
    assert_failed(await bench.write("level", "2.5 dimensionless"), "not a whole number")
    assert_done(await bench.write("level", "3 dimensionless"))
    await eventually(lambda: asyncio.sleep(0, bool(robot.ops("publish"))))
    assert robot.ops("publish")[-1]["msg"] == {"level": 3}
    await bench.close()


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { battery: { unit: percent } }", "needs a map"),
        ("read: { frame: { type: image, map: { topic: /camera, field: data } } }", "doesn't read images"),
        ("read: { battery: { unit: V, map: { service: /x, field: data } } }", "exactly one of topic"),
        ("read: { battery: { unit: V, map: { topic: cmd_vel, field: data } } }", "String should match"),
        ("read: { battery: { unit: V, map: { topic: /x, field: 'a..b' } } }", "String should match"),
        (
            "write: { drive: { unit: m/s, min: 0, max: 1, map: { topic: /cmd_vel, field: linear.x } } }",
            "publishing needs type",
        ),
        (
            "write: { drive: { unit: m/s, min: 0, max: 1, map: { topic: /cmd_vel, type: bad, field: x } } }",
            "String should match",
        ),
        ("actions: { go: { map: { action: /go } } }", "need type"),
        ("actions: { go: { map: { service: /go, args: { x: 'a b' } } } }", "field path"),
        ("actions: { go: { args: { x: { unit: m, min: 0, max: 1 } }, map: { service: /go } } }", "must match"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ ros2: localhost }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        Ros2Driver(loads(text))


@pytest.mark.parametrize(
    ("params", "message"), [("timeout: 0 s", "timeout"), ("action_wait: 30 s", "action_wait"), ("path: nope", "path")]
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Ros2Driver(loads(f"device: Bad\nid: bad\nconnect: {{ ros2: localhost, {params} }}\n"))


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/ros2/examples/turtlebot4.hal.yaml")
    assert not file.writable
    assert file.effective_hazard == "high"
    driver = Ros2Driver(file)
    assert "cmd_vel_linear" in driver.writes
