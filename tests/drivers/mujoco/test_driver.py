"""The mujoco driver on the bench arm, through a real kernel. Skipped when the mujoco extra isn't installed."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest

mujoco = pytest.importorskip("mujoco")

from openhal.drivers.base import DriverError  # noqa: E402
from openhal.drivers.mujoco.conformance import BENCH_ARM  # noqa: E402
from openhal.drivers.mujoco.driver import MujocoDriver  # noqa: E402
from openhal.drivers.mujoco.maps import MujocoParams, Scale, default_loader, scale  # noqa: E402
from openhal.drivers.mujoco.simulator import World  # noqa: E402
from openhal.spec import loads  # noqa: E402
from tests.drivers.serial.kit import Bench, assert_done, assert_failed, eventually  # noqa: E402

ARM = """
device: Bench arm
id: arm
connect: { mujoco: OPENHAL_TEST_ARM, keyframe: rest, action_wait: 4 s }
read:
  pan: { unit: deg, range: [-30, 30] }
  lift: { unit: rad }
  finger: { unit: percent }
  tip_z: { unit: mm, map: { site: tip, axis: z } }
  block_y: { unit: mm, map: { body: block, axis: y } }
write:
  pan_goal: { unit: deg, min: -90, max: 90, max_change_per_s: 90 }
  lift_goal: { unit: deg, min: -85, max: 85, max_change_per_s: 90 }
  elbow_goal: { unit: deg, min: -140, max: 140, max_change_per_s: 90 }
  wrist_goal: { unit: deg, min: -110, max: 110, max_change_per_s: 90 }
  finger_goal: { unit: percent, min: 0, max: 100, max_change_per_s: 400 }
actions:
  move_to:
    args:
      x: { unit: mm, min: 100, max: 400 }
      y: { unit: mm, min: -100, max: 100 }
      z: { unit: mm, min: 0, max: 150 }
    map: { command: move_to, site: tip, aim: { axis: [1, 0, 0], toward: [0, 0, -2] } }
    effects: [pan_goal, lift_goal, elbow_goal, wrist_goal]
  drop:
    args:
      height: { unit: cm, min: 3, max: 12 }
    map:
      command: move_to
      site: tip
      axes: { height: z }
      at: { x: 180 mm, y: "0.04 m" }
      then: { finger_goal: 100 }
    effects: [pan_goal, lift_goal, elbow_goal, wrist_goal, finger_goal]
  hold: {}
safe_state: { action: hold }
hazard: medium
confirmed: { by: tester, at: 2026-11-02 }
"""


def model(xml: str = BENCH_ARM) -> object:
    return mujoco.MjModel.from_xml_string(xml)


def make(text: str = ARM, xml: str = BENCH_ARM) -> tuple[MujocoDriver, Bench]:
    file = loads(text)
    driver = MujocoDriver(file, loader=lambda: model(xml))
    return driver, Bench(file, driver)


def edit(old: str, new: str, text: str = ARM) -> str:
    assert old in text
    return text.replace(old, new)


async def _moving(world: World) -> bool:
    return bool(world.motions)


async def _near(bench: Bench, channel: str, wanted: float, within: float) -> bool:
    value = (await bench.read(channel)).value
    assert isinstance(value, float)
    return abs(value - wanted) <= within


async def test_connect_starts_the_world_from_its_keyframe() -> None:
    driver, bench = make()
    await bench.connect()
    assert driver.simulated
    assert (await bench.read("lift")).value == pytest.approx(-0.9, abs=0.01)
    assert (await bench.read("finger")).value == pytest.approx(100 / 3, abs=0.5)
    assert (await bench.read("pan_goal")).value == pytest.approx(0.0)
    assert (await bench.read("finger_goal")).value == pytest.approx(100 / 3)
    assert (await bench.read("tip_z")).value == pytest.approx(43, abs=2)
    assert (await bench.read("block_y")).value == pytest.approx(100, abs=1)
    identity = await driver.identify()
    assert identity["model"] == "bench arm"
    assert identity["joints"] == "pan, lift, elbow, wrist, finger, block"
    assert identity["actuators"] == "pan, lift, elbow, wrist, finger"
    assert identity["timestep"] == "0.002 s"
    assert identity["simulated"] == "true"
    health = await driver.health()
    assert health.connected
    assert "s simulated" in health.detail
    await bench.close()


async def test_a_goal_moves_at_the_channel_speed_and_reads_back() -> None:
    _driver, bench = make()
    await bench.connect()
    await asyncio.sleep(1.2)
    assert_done(await bench.write("pan_goal", "45 deg"))
    assert (await bench.read("pan_goal")).value == pytest.approx(45)
    reading = await bench.read("pan")
    assert reading.value < 45
    await eventually(lambda: _near(bench, "pan", 45, 0.5), within=5)
    assert (await bench.read("pan")).suspect
    await bench.close()


async def test_a_percent_channel_spans_the_range() -> None:
    driver, bench = make()
    await bench.connect()
    await asyncio.sleep(0.3)
    assert_done(await bench.write("finger_goal", "100 %"))
    assert driver.world is not None
    world = driver.world

    async def opened() -> bool:
        return bool(world.data.ctrl[4] == pytest.approx(0.03))

    await eventually(opened, within=5)
    await eventually(lambda: _near(bench, "finger", 100, 1), within=5)
    await bench.close()


async def test_move_to_puts_the_site_at_the_point_pointing_down() -> None:
    driver, bench = make()
    await bench.connect()
    decision = await bench.act("move_to", x="200 mm", y="40 mm", z="60 mm")
    assert_done(decision)
    assert driver.world is not None
    tip = mujoco.mj_name2id(driver.world.model, mujoco.mjtObj.mjOBJ_SITE, "tip")
    assert driver.world.site_position(tip) == pytest.approx((0.2, 0.04, 0.06), abs=3e-3)
    lift = (await bench.read("lift_goal")).value
    assert isinstance(lift, float)
    assert lift == pytest.approx(math.degrees(driver.world.data.ctrl[1]))
    await bench.close()


async def test_move_to_out_of_reach_fails_in_the_driver() -> None:
    _driver, bench = make()
    await bench.connect()
    decision = await bench.act("move_to", x="400 mm", y="0 mm", z="0 mm")
    assert_failed(decision, "move_to can't reach 400.0, 0.0, 0.0 mm with that aim inside the joint limits.")
    await bench.close()


async def test_a_fixed_point_then_opens_the_finger() -> None:
    driver, bench = make()
    await bench.connect()
    await asyncio.sleep(0.2)
    assert driver.world is not None
    result = await driver._action("drop", {"height": 8.0})
    assert result["status"] == "done"
    assert result["to_mm"] == "180.0, 40.0, 80.0"
    assert set(result["goals"]) == {"pan_goal", "lift_goal", "elbow_goal", "wrist_goal"}
    assert driver.world.data.ctrl[4] == pytest.approx(0.03)
    await bench.close()


async def test_a_long_move_returns_started_and_keeps_going() -> None:
    driver, bench = make(edit("action_wait: 4 s", "action_wait: 100 ms"))
    await bench.connect()
    result = await driver._action("move_to", {"x": 150.0, "y": -80.0, "z": 120.0})
    assert result["status"] == "started"
    assert driver.world is not None
    assert driver.world.motions
    await bench.close()


async def test_a_hold_during_a_move_ends_it_held() -> None:
    driver, bench = make()
    await bench.connect()
    assert driver.world is not None
    world = driver.world
    task = asyncio.create_task(driver._action("move_to", {"x": 150.0, "y": -80.0, "z": 120.0}))
    await eventually(lambda: _moving(world), within=5)
    world.hold()
    assert (await task)["status"] == "held"
    await bench.close()


async def test_a_stop_freezes_the_arm_where_it_stands() -> None:
    driver, bench = make()
    await bench.connect()
    assert driver.world is not None
    world = driver.world
    move = asyncio.create_task(bench.act("move_to", x="150 mm", y="-80 mm", z="120 mm"))
    await eventually(lambda: _moving(world), within=5)
    await asyncio.sleep(0.2)
    assert await bench.stop() == "safe"
    stopped = [world.qpos(joint) for joint in range(4)]
    assert (await move).code == "stopped"
    await asyncio.sleep(0.3)
    frozen = [world.qpos(joint) for joint in range(4)]
    assert frozen == pytest.approx(stopped, abs=math.radians(2))
    await asyncio.sleep(0.5)
    assert [world.qpos(joint) for joint in range(4)] == pytest.approx(frozen, abs=math.radians(0.05))
    assert world.motions == []
    assert_done(await bench.act("hold"))
    await bench.close()


async def test_health_reports_a_world_that_stopped() -> None:
    driver, bench = make()
    assert (await driver.health()).detail == "not connected"
    assert await driver.describe() is None
    await bench.connect()
    assert driver.world is not None
    driver.world.failure = "the simulation became unstable and MuJoCo reset it"
    assert (await driver.health()).detail == "the simulation became unstable and MuJoCo reset it"
    driver.world.failure = None
    driver.world.close()
    assert (await driver.health()).detail == "the simulation is not running"
    await bench.close()
    await bench.close()
    await driver._safe_state()
    with pytest.raises(DriverError, match="arm is not connected"):
        await driver.read("pan")


async def test_unknown_channels_and_values_fail() -> None:
    driver, bench = make()
    await bench.connect()
    with pytest.raises(DriverError, match="no channel 'nope'"):
        await driver.read("nope")
    with pytest.raises(DriverError, match="no write channel 'pan'"):
        await driver._write("pan", 1.0)
    with pytest.raises(DriverError, match="pan_goal needs a number"):
        await driver._write("pan_goal", True)
    with pytest.raises(DriverError, match="no action 'wave'"):
        await driver._action("wave", {})
    await bench.close()


async def test_the_model_comes_from_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    load = default_loader("OPENHAL_TEST_ARM")
    monkeypatch.delenv("OPENHAL_TEST_ARM", raising=False)
    with pytest.raises(DriverError, match="Set the OPENHAL_TEST_ARM environment variable"):
        load()
    monkeypatch.setenv("OPENHAL_TEST_ARM", str(tmp_path / "missing.xml"))
    with pytest.raises(DriverError, match="MuJoCo could not load the model named by OPENHAL_TEST_ARM"):
        load()
    (tmp_path / "arm.xml").write_text(BENCH_ARM, encoding="utf-8")
    monkeypatch.setenv("OPENHAL_TEST_ARM", str(tmp_path / "arm.xml"))
    driver = MujocoDriver(loads(edit("keyframe: rest,", "keyframe: rest, timestep: 4 ms,")))
    await driver.connect()
    assert driver.world is not None
    assert driver.world.timestep == pytest.approx(0.004)
    await driver.close()


async def test_describe_proposes_channels_from_the_model() -> None:
    xml = BENCH_ARM.replace('name="wrist"', 'name="Wrist-2"').replace('joint="wrist"', 'joint="Wrist-2"')
    xml = xml.replace('<position name="Wrist-2"', '<position name="9wrist"').replace(
        '<joint name="finger" type="slide" axis="0 1 0" range="0 0.03"/>',
        '<joint name="finger" type="slide" axis="0 1 0"/>',
    )
    xml = xml.replace('ctrlrange="0 0.03" kp="200"', 'kp="200"').replace(
        'joint="lift" ctrlrange="-1.5 1.5"', 'joint="lift"'
    )
    xml = xml.replace("</actuator>", '<motor name="spin" site="tip" gear="0 0 0 1 0 0"/></actuator>')
    text = edit("  finger: { unit: percent }\n", "").replace("wrist_goal", "spare_goal")
    text = text.replace("spare_goal: { unit: deg", 'spare_goal: { map: { actuator: spin, unit: "N*m" }, unit: "N*m"')
    text = text.replace("min: -110, max: 110, max_change_per_s: 90 }", "min: -1, max: 1 }")
    text = text.replace("finger_goal: { unit: percent", "finger_goal: { unit: mm").replace("max: 100,", "max: 30,")
    text = text.replace("then: { finger_goal: 100 }", "then: { finger_goal: 30 }")
    text = text.replace(", spare_goal]", "]").replace("spare_goal, ", "")
    driver, bench = make(text, xml)
    await bench.connect()
    described = await driver.describe()
    assert described is not None
    assert set(described["read"]) == {"pan", "lift", "elbow", "wrist_2", "finger"}
    assert described["read"]["finger"] == {"unit": "mm"}
    assert set(described["write"]) == {"pan_goal", "lift_goal", "elbow_goal", "finger_goal"}
    assert described["write"]["pan_goal"] == {"unit": "deg", "suggested": True, "min": -114.6, "max": 114.6}
    assert described["write"]["finger_goal"] == {"unit": "mm", "suggested": True}
    assert described["write"]["lift_goal"] == {"unit": "deg", "suggested": True, "min": -85.9, "max": 85.9}
    assert described["device"] == {"name": "bench arm (simulated)"}
    assert described["safe_state"] == [{"action": "hold"}]
    assert_done(await bench.write("spare_goal", "0.5 N*m"))
    await bench.close()


def test_scales_convert_units_and_percent() -> None:
    assert scale(None, "rad", None, "here") == Scale(1.0, 0.0)
    degrees = scale("deg", "rad", None, "here")
    assert degrees.native(180) == pytest.approx(math.pi)
    assert degrees.channel(math.pi / 2) == pytest.approx(90)
    percent = scale("%", "m", (0.0, 0.03), "here")
    assert percent.native(50) == pytest.approx(0.015)
    with pytest.raises(DriverError, match="here is in percent, which needs a limited range in the model"):
        scale("percent", "rad", None, "here")
    with pytest.raises(DriverError, match="here is in rad in the model, which doesn't convert to mm"):
        scale("mm", "rad", None, "here")


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"model_env": "lower"}, "String should match pattern"),
        ({"model_env": "X", "timestep": "1 h"}, "timestep must be between"),
        ({"model_env": "X", "action_wait": "20 s"}, "action_wait must be between"),
        ({"model_env": "X", "tolerance": "3 deg"}, "tolerance needs a length such as 1 mm"),
        ({"model_env": "X", "tolerance": "1 m"}, "tolerance must be between"),
        ({"model_env": "X", "aim_tolerance": "1 mm"}, "aim_tolerance needs an angle such as 3 deg"),
        ({"model_env": "X", "aim_tolerance": "90 deg"}, "aim_tolerance must be between"),
    ],
)
def test_parameters_are_checked(params: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        MujocoParams.model_validate(params)


def test_parameters_take_quantities() -> None:
    settings = MujocoParams.model_validate({"model_env": "X", "tolerance": "2 mm", "aim_tolerance": "5 deg"})
    assert settings.tolerance == pytest.approx(0.002)
    assert settings.aim_tolerance == pytest.approx(math.radians(5))
    assert settings.timestep is None


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("  lift: { unit: rad }", "  lift: { type: bool }", "read.lift: positions are numbers"),
        ("{ site: tip, axis: z }", "{ site: tip }", "a site or a body needs an axis"),
        ("{ site: tip, axis: z }", "{ site: tip, joint: pan }", "give exactly one of joint, site or body"),
        (
            "  pan_goal: { unit: deg,",
            "  pan_goal: { map: { motor: pan }, unit: deg,",
            "write.pan_goal.map is not valid",
        ),
        ("  hold: {}\nsafe_state: { action: hold }", "  wave: {}\nsafe_state: { action: wave }", "wave needs a map"),
        ("  hold: {}", "  hold: { map: { command: hold, site: tip } }", "hold takes nothing but the command"),
        (
            "  hold: {}",
            "  hold: {}\n  park: { args: { x: { unit: mm, min: 0, max: 1 } }, map: { command: hold } }",
            "takes no",
        ),
        ("command: move_to, site: tip, aim", "command: move_to, aim", "move_to needs the site to move"),
        ("toward: [0, 0, -2]", "toward: [0, 0, 0]", "three numbers that aren't all zero"),
        ("axes: { height: z }", "axes: { height: z, depth: x }", "map.axes names depth, which aren't arguments"),
        ("      axes: { height: z }\n", "", "map.axes must name an axis for height"),
        ("height: { unit: cm,", "height: { unit: s,", "drop.args.height is a coordinate"),
        ('at: { x: 180 mm, y: "0.04 m" }', "at: { x: 180 mm }", "x, y and z each come from one argument"),
        ("then: { finger_goal: 100 }", "then: { finger: 100 }", "then names finger, which is not a write channel"),
        ("then: { finger_goal: 100 }", "then: { finger_goal: 120 }", "sets finger_goal to 120, outside its limits"),
        ("wrist_goal, finger_goal]", "wrist_goal]", "drop changes finger_goal, so list it in effects"),
        ("at: { x: 180 mm,", "at: { x: 180 s,", "at.x needs a length"),
        ('at: { x: 180 mm, y: "0.04 m" }', "at: 5", "actions.drop.map is not valid"),
    ],
)
def test_maps_are_checked_when_the_driver_is_built(old: str, new: str, message: str) -> None:
    with pytest.raises(DriverError, match=message):
        MujocoDriver(loads(edit(old, new)))


def test_a_write_channel_must_be_a_number() -> None:
    text = edit("  finger_goal: { unit: percent, min: 0, max: 100, max_change_per_s: 400 }", "  light: { type: bool }")
    text = text.replace(", finger_goal]", "]").replace("then: { finger_goal: 100 }", "then: {}")
    with pytest.raises(DriverError, match=r"write\.light: actuator goals are numbers"):
        MujocoDriver(loads(text))


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("  lift: { unit: rad }", "  lift: { unit: rad, map: { joint: shoulder } }", "has no joint named 'shoulder'"),
        ("{ site: tip, axis: z }", "{ site: nose, axis: z }", "has no site named 'nose'"),
        ("{ body: block, axis: y }", "{ body: crate, axis: y }", "has no body named 'crate'"),
        ("  lift: { unit: rad }", "  lift: { unit: rad, map: { joint: block } }", "block is a free or ball joint"),
        ("  lift: { unit: rad }", "  lift: { unit: mm }", "read.lift is in rad in the model"),
        ("  pan_goal: { unit: deg,", "  pan_goal: { map: { actuator: yaw }, unit: deg,", "has no actuator named 'yaw'"),
        ("keyframe: rest", "keyframe: dance", "The model has no keyframe named 'dance'"),
        ("lift_goal, elbow_goal, wrist_goal]\n  drop", "lift_goal, elbow_goal]\n  drop", "move_to moves wrist_goal"),
    ],
)
async def test_maps_are_checked_against_the_model(old: str, new: str, message: str) -> None:
    driver, bench = make(edit(old, new))
    with pytest.raises(DriverError, match=message):
        await driver.connect()
    await bench.close()


async def test_bindings_need_joints_that_move_the_site_and_a_unit_for_other_actuators() -> None:
    xml = BENCH_ARM.replace('<freejoint name="block"/>', '<freejoint name="block"/><site name="mark"/>')
    driver, bench = make(edit("command: move_to, site: tip, aim", "command: move_to, site: mark, aim"), xml)
    with pytest.raises(DriverError, match="no write channel drives a joint that moves mark"):
        await driver.connect()
    await bench.close()
    xml = BENCH_ARM.replace("</actuator>", '<motor name="spin" site="tip" gear="0 0 0 1 0 0"/></actuator>')
    driver, bench = make(edit("  pan_goal: { unit: deg,", "  pan_goal: { map: { actuator: spin }, unit: deg,"), xml)
    with pytest.raises(DriverError, match=r"spin doesn't drive a joint, so give its unit in map\.unit"):
        await driver.connect()
    await bench.close()


async def test_a_geared_actuator_and_an_open_joint_range() -> None:
    xml = BENCH_ARM.replace('<joint name="pan" axis="0 0 1" range="-2 2"/>', '<joint name="pan" axis="0 0 1"/>')
    xml = xml.replace(
        '<position name="pan" joint="pan" ctrlrange="-2 2"/>', '<position name="pan" joint="pan" gear="2"/>'
    )
    text = edit("  pan_goal: { unit: deg, min: -90, max: 90,", "  pan_goal: { unit: rad, min: -3, max: 3,")
    driver, bench = make(text, xml)
    await bench.connect()
    result = await driver._action("move_to", {"x": 200.0, "y": 40.0, "z": 60.0})
    assert result["status"] == "done"
    assert driver.world is not None
    goal = float(driver.world.data.ctrl[0])
    assert result["goals"]["pan_goal"] == pytest.approx(goal, abs=1e-3)
    assert driver.world.qpos(0) == pytest.approx(goal / 2, abs=0.01)
    await bench.close()
