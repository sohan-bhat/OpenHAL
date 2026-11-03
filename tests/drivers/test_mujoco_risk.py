"""A simulated arm's joint goals are high risk from what they are, with no rule for the mujoco driver (ADR 0023)."""

from __future__ import annotations

from pathlib import Path

import pytest

from openhal.spec import risk
from openhal.spec.loader import from_data, load
from openhal.spec.models import DeviceFile

mujoco = pytest.importorskip("mujoco")

from openhal.drivers.mujoco.conformance import BENCH_ARM, FILE  # noqa: E402
from openhal.drivers.mujoco.driver import MujocoDriver  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def writable(file: DeviceFile) -> dict[str, str]:
    return {target: found.level for target, found in risk.assess(file).items() if not target.startswith("read:")}


async def described(xml: str) -> dict[str, object]:
    probe = from_data({"device": "Probe", "connect": {"driver": "mujoco", "params": dict(FILE.connect.params)}})
    driver = MujocoDriver(probe, loader=lambda: mujoco.MjModel.from_xml_string(xml))
    await driver.connect()
    try:
        sections = await driver.describe()
    finally:
        await driver.close()
    assert sections is not None
    sections.pop("device")
    return sections


async def test_every_goal_the_driver_describes_is_high() -> None:
    sections = await described(BENCH_ARM)
    file = from_data({"device": "Bench arm (simulated)", "connect": {"driver": "mock"}, **sections})
    levels = writable(file)
    assert {target for target in levels if target.startswith("write:")} >= {"write:pan_goal", "write:elbow_goal"}
    assert set(levels.values()) == {"high"}
    assert file.unconfirmed(), "a fresh arm stays read-only until a person confirms its limits"


async def test_goals_with_no_telling_names_are_high_from_their_axes() -> None:
    plain = BENCH_ARM
    for name in ("pan", "lift", "elbow", "wrist", "finger"):
        plain = plain.replace(f'<position name="{name}"', f'<position name="a_{name[:1]}"')
    sections = await described(plain)
    file = from_data({"device": "Bench rig (simulated)", "connect": {"driver": "mock"}, **sections})
    goals = {target: level for target, level in writable(file).items() if target.endswith("_goal")}
    assert len(goals) == 5
    assert set(goals.values()) == {"high"}


def test_the_conformance_arm_and_the_so101_scene_are_high() -> None:
    assert set(writable(FILE).values()) == {"high"}
    scene = ROOT / "video" / "hub" / "so101-sim.hal.yaml"
    if scene.exists():
        levels = writable(load(scene))
        assert {levels[f"write:{joint}_goal"] for joint in ("shoulder_pan", "elbow_flex", "wrist_roll", "gripper")} == {
            "high"
        }
        assert levels["action:move_to"] == "high"
