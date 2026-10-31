"""The LeRobot driver, against the faithful fake of LeRobot's SOFollower."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from openhal.drivers.base import DriverError
from openhal.drivers.lerobot.driver import LeRobotDriver
from openhal.drivers.lerobot.simulator import FakeFactory, FakeFollower
from openhal.spec import load, loads
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually

ARM = """
device: Test arm
id: arm
connect:
  lerobot: so101_follower
  port: /dev/ttyACM0
  robot_id: test_arm
  timeout: 500 ms
  action_wait: 2 s
  observation_age: 0 s
read:
  shoulder_pan: { unit: deg, range: [-110, 110] }
  elbow_flex: { unit: rad }
  gripper: { unit: percent }
  torque: { type: bool }
write:
  shoulder_pan_goal: { unit: deg, min: -45, max: 45 }
  gripper_goal: { unit: percent, min: 0, max: 60 }
actions:
  torque_off: {}
  torque_on: {}
  pose:
    args: { pan: { unit: deg, min: -45, max: 45 }, lift: { unit: deg, min: -100, max: 0 } }
    map: { command: move, joints: { pan: shoulder_pan, lift: shoulder_lift } }
safe_state: { gripper_goal: 0 }
hazard: high
confirmed: { by: tester, at: 2026-10-24 }
"""


def make(text: str = ARM, factory: FakeFactory | None = None) -> tuple[LeRobotDriver, FakeFactory, Bench]:
    fake = factory or FakeFactory()
    file = loads(text)
    driver = LeRobotDriver(file, robot_factory=fake)
    return driver, fake, Bench(file, driver)


def arm(factory: FakeFactory) -> FakeFollower:
    assert factory.arm is not None
    return factory.arm


async def _value(bench: Bench, channel: str, wanted: object) -> bool:
    return (await bench.read(channel)).value == wanted


async def test_connect_never_calibrates_and_holds_position() -> None:
    driver, factory, bench = make()
    await bench.connect()
    config = factory.configs[0]
    assert (config.port, config.id, config.use_degrees, config.cameras) == ("/dev/ttyACM0", "test_arm", True, {})
    assert config.disable_torque_on_disconnect is True
    assert arm(factory).calls[0] == ("connect", {"calibrate": False})
    assert (await bench.read("torque")).value is True
    identity = await driver.identify()
    assert identity["joints"] == "shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll, gripper"
    assert identity["calibrated"] == "true"
    assert (await driver.health()).connected
    await bench.close()


async def test_an_uncalibrated_arm_is_refused() -> None:
    _driver, factory, bench = make(factory=FakeFactory(calibrated=False))
    with pytest.raises(DriverError, match=r"Run lerobot-calibrate --robot\.type=so101_follower"):
        await bench.connect()
    assert arm(factory).calls == []


async def test_joint_positions_in_the_channel_units() -> None:
    _driver, factory, bench = make()
    await bench.connect()
    assert (await bench.read("shoulder_pan")).value == 0.0
    assert (await bench.read("elbow_flex")).value == pytest.approx(1.5708, abs=1e-4)
    assert (await bench.read("gripper")).value == 10.0
    arm(factory).present["shoulder_pan"] = 150.0
    assert (await bench.read("shoulder_pan")).suspect
    await bench.close()


async def test_goal_positions_move_the_joint() -> None:
    _driver, factory, bench = make()
    await bench.connect()
    assert_done(await bench.write("shoulder_pan_goal", "30 deg"))
    assert arm(factory).calls[-1] == ("send_action", {"shoulder_pan": 30.0})
    assert (await bench.read("shoulder_pan_goal")).value == 30.0
    await eventually(lambda: _value(bench, "shoulder_pan", 30.0))
    await bench.close()


async def test_lerobot_clipping_shows_in_the_readback() -> None:
    text = ARM.replace("robot_id: test_arm\n", "robot_id: test_arm\n  max_relative_target: 5\n")
    _driver, factory, bench = make(text)
    await bench.connect()
    assert factory.configs[0].max_relative_target == 5
    assert_done(await bench.write("shoulder_pan_goal", "40 deg"))
    assert (await bench.read("shoulder_pan_goal")).value == pytest.approx(5.0)
    await bench.close()


async def test_kernel_limits_stop_goals_before_lerobot() -> None:
    text = ARM.replace("min: -45, max: 45 }", "min: -45, max: 45, max_change_per_s: 10 }", 1)
    _driver, factory, bench = make(text)
    await bench.connect()
    assert (await bench.write("shoulder_pan_goal", "90 deg")).code == "above_max"
    assert (await bench.write("shoulder_pan_goal", "40 deg")).code == "rate_limited"
    assert (await bench.write("gripper_goal", "80 %")).status == "blocked"
    assert [call for call in arm(factory).calls if call[0] == "send_action"] == []
    await bench.close()


async def test_move_action_sends_one_action_for_several_joints() -> None:
    _driver, factory, bench = make()
    await bench.connect()
    assert_done(await bench.act("pose", pan="10 deg", lift="-80 deg"))
    assert arm(factory).calls[-1] == ("send_action", {"shoulder_pan": 10.0, "shoulder_lift": -80.0})
    assert arm(factory).present["shoulder_lift"] == pytest.approx(-80.0, abs=2.0)
    await bench.close()


async def test_slow_move_returns_started() -> None:
    text = ARM.replace("action_wait: 2 s", "action_wait: 200 ms")
    _driver, factory, bench = make(text)
    await bench.connect()
    arm(factory).speed = 1.0
    decision = await bench.act("pose", pan="40 deg", lift="-90 deg")
    assert_done(decision)
    assert arm(factory).present["shoulder_pan"] < 5
    await bench.close()


async def test_stop_turns_torque_off_and_the_arm_stops_following() -> None:
    _driver, factory, bench = make()
    await bench.connect()
    arm(factory).speed = 5.0
    assert_done(await bench.write("shoulder_pan_goal", "40 deg"))
    assert await bench.stop() == "safe"
    assert ("disable_torque", {}) in arm(factory).calls
    assert (await bench.read("torque")).value is False
    held = arm(factory).positions()["shoulder_pan"]
    await asyncio.sleep(0.1)
    assert arm(factory).positions()["shoulder_pan"] == pytest.approx(held)
    assert (await bench.read("shoulder_pan_goal")).value == pytest.approx(held)
    assert_done(await bench.act("torque_on"))
    name, goals = arm(factory).calls[-2]
    assert name == "send_action"
    assert goals["shoulder_pan"] == pytest.approx(held)
    assert arm(factory).calls[-1] == ("enable_torque", {})
    assert (await bench.read("torque")).value is True
    await asyncio.sleep(0.1)
    assert arm(factory).positions()["shoulder_pan"] == pytest.approx(held)
    assert_done(await bench.act("torque_off"))
    await bench.close()


async def test_close_turns_torque_off_unless_asked_not_to() -> None:
    _driver, factory, bench = make()
    await bench.connect()
    await bench.close()
    assert arm(factory).bus.torque is False
    text = ARM.replace("robot_id: test_arm\n", "robot_id: test_arm\n  torque_off_on_close: false\n")
    _driver, factory, bench = make(text)
    await bench.connect()
    await bench.close()
    assert arm(factory).bus.torque is True


async def test_bus_failures_and_reconnect() -> None:
    driver, factory, bench = make()
    await bench.connect()
    arm(factory).fail_next = 1
    assert_failed(await bench.write("gripper_goal", "20 %"), "bus failed")
    assert not (await driver.health()).connected
    await bench.connect()
    assert (await driver.health()).connected
    arm(factory).lost = True
    with pytest.raises(DriverError, match="bus failed"):
        await driver.read("shoulder_pan")
    factory.lost = True
    with pytest.raises(DriverError, match="Could not connect"):
        await bench.connect()
    factory.lost = False
    await bench.connect()
    assert (await bench.read("gripper")).value == 10.0
    await bench.close()


async def test_a_stalled_bus_times_out() -> None:
    driver, factory, bench = make()
    await bench.connect()
    arm(factory).latency_s = 2.0
    with pytest.raises(TimeoutError, match="sent no reply to reading the joints"):
        await driver.read("shoulder_pan")
    arm(factory).latency_s = 0.0
    await bench.close()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("  elbow_flex: { unit: rad }", "  elbow: { unit: rad }", "has no joint 'elbow'"),
        ("  gripper: { unit: percent }", "  gripper: { unit: degC }", "doesn't convert"),
        ("lift: shoulder_lift", "lift: hip", "has no joint 'hip'"),
    ],
)
async def test_connect_refuses_files_that_do_not_fit_the_arm(old: str, new: str, message: str) -> None:
    assert old in ARM
    driver, factory, bench = make(ARM.replace(old, new))
    with pytest.raises(DriverError, match=message):
        await bench.connect()
    assert driver.robot is None
    assert arm(factory).calls[-1] == ("disconnect", {})


NORMALIZED = """
device: Normalized arm
id: arm
connect: { lerobot: so101_follower, port: /dev/ttyACM0, robot_id: test_arm, use_degrees: false, timeout: 500 ms }
read:
  elbow_flex: { unit: dimensionless }
write:
  shoulder_pan_goal: { unit: dimensionless, min: -50, max: 50 }
"""


async def test_normalized_range_without_degrees() -> None:
    _driver, factory, bench = make(NORMALIZED)
    await bench.connect()
    assert factory.configs[0].use_degrees is False
    assert (await bench.read("elbow_flex")).unit == "dimensionless"
    await bench.close()
    with pytest.raises(DriverError, match="doesn't convert"):
        await make(NORMALIZED.replace("elbow_flex: { unit: dimensionless }", "elbow_flex: { unit: deg }"))[2].connect()


async def test_lerobot_missing_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "lerobot", None)
    monkeypatch.setitem(sys.modules, "lerobot.robots", None)
    driver = LeRobotDriver(loads(ARM))
    with pytest.raises(DriverError, match="LeRobot isn't installed"):
        await driver.connect()


async def test_describe_proposes_tight_goal_limits() -> None:
    driver, _factory, bench = make()
    assert await driver.describe() is None
    await bench.connect()
    proposal = await driver.describe()
    assert proposal is not None
    assert proposal["write"]["shoulder_lift_goal"]["min"] == -100.0
    assert proposal["write"]["shoulder_lift_goal"]["max"] == -80.0
    assert proposal["write"]["gripper_goal"] == {
        "unit": "percent",
        "min": 0.0,
        "max": 20.0,
        "max_change_per_s": 20,
        "confirm": "confirm-each-time",
        "suggested": True,
    }
    assert all(entry["suggested"] for entry in [*proposal["write"].values(), *proposal["actions"].values()])
    await bench.close()


async def test_discover_lists_usb_serial_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    class Port:
        device = "/dev/ttyACM0"
        vid, pid = 0x1A86, 0x55D3
        serial_number = "5A46"
        manufacturer = None
        product = "USB Single Serial"
        description = "USB Single Serial"

    monkeypatch.setattr("openhal.drivers.lerobot.driver.list_serial_ports", lambda: [Port()])
    found = await LeRobotDriver.discover()
    assert found[0].identifiers["usb"] == "1a86:55d3"


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("read: { torque: { unit: deg } }", "torque reads as true or false"),
        ("read: { elbow_flex: { type: bool } }", "a joint position is a number"),
        ("read: { both: { unit: deg, map: { joint: elbow_flex, torque: true } } }", "give a joint, or torque"),
        ("write: { grip: { type: bool } }", "goal positions are numbers"),
        ("actions: { wave: { map: { command: dance } } }", "String should match"),
        ("actions: { torque_off: { args: { x: { unit: deg, min: 0, max: 1 } } } }", "takes no arguments"),
        (
            "actions: { pose: { args: { x: { unit: deg, min: 0, max: 1 } }, map: { command: move } } }",
            "name a joint for each",
        ),
        ("actions: { pose: {} }", "needs a map"),
    ],
)
def test_bad_maps_are_rejected(snippet: str, message: str) -> None:
    text = f"device: Bad\nid: bad\nconnect: {{ lerobot: so101_follower, port: /dev/x, robot_id: a }}\n{snippet}\n"
    with pytest.raises(DriverError, match=message):
        LeRobotDriver(loads(text), robot_factory=FakeFactory())


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ("robot_id: a, timeout: 0 s", "timeout"),
        ("robot_id: a, max_relative_target: 500", "max_relative_target"),
        ("robot_id: 'a b'", "robot_id"),
    ],
)
def test_bad_params_are_rejected(params: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        LeRobotDriver(loads(f"device: Bad\nid: bad\nconnect: {{ lerobot: so101_follower, port: /dev/x, {params} }}\n"))


def test_example_file_loads_read_only() -> None:
    file = load(Path(__file__).parents[3] / "openhal/drivers/lerobot/examples/so101-follower.hal.yaml")
    assert not file.writable
    assert file.effective_hazard == "high"
    driver = LeRobotDriver(file)
    assert "shoulder_pan_goal" in driver.writes
